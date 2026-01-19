"""Generate Phase 1 output artifacts."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

from ..models.category import CategoryDefinition
from ..models.outputs import CategoriesOutput, ExtractionLog, PageSummary, TriageResult
from ..models.page import ConfluencePage, PageValue

console = Console()


class OutputGenerator:
    """Generate Phase 1 outputs."""

    def __init__(self, output_dir: Path):
        """Initialize output generator.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(
        self,
        pages: list[ConfluencePage],
        categories: list[CategoryDefinition],
        extraction_start: datetime,
        space_key: str,
    ) -> None:
        """Generate all Phase 1 outputs.

        Args:
            pages: All extracted pages
            categories: Category definitions
            extraction_start: When extraction started
            space_key: Confluence space key
        """
        console.print("\n[cyan]Generating Phase 1 outputs...[/cyan]")

        # Generate each artifact
        self.generate_extraction_log(pages, extraction_start, space_key)
        self.generate_categories(categories)
        self.generate_high_value_pages(pages)
        self.generate_triage_notes(pages, categories)

        console.print("[green]All Phase 1 outputs generated successfully![/green]\n")
        console.print(f"[cyan]Output directory: {self.output_dir.absolute()}[/cyan]")

    def generate_extraction_log(
        self,
        pages: list[ConfluencePage],
        extraction_start: datetime,
        space_key: str,
    ) -> None:
        """Generate extraction-log.yaml.

        Args:
            pages: All extracted pages
            extraction_start: When extraction started
            space_key: Confluence space key
        """
        page_summaries = [
            PageSummary(
                page_id=p.metadata.page_id,
                title=p.metadata.title,
                url=p.metadata.url,
                category=p.category.value if hasattr(p.category, 'value') else str(p.category),
                value=p.value,
                last_modified=p.metadata.last_modified,
                inbound_link_count=p.metadata.inbound_link_count,
            )
            for p in pages
        ]

        log = ExtractionLog(
            extraction_started=extraction_start,
            extraction_completed=datetime.utcnow(),
            space_key=space_key,
            total_pages=len(pages),
            processed_pages=sum(1 for p in pages if p.processed),
            pages=page_summaries,
        )

        output_file = self.output_dir / "extraction-log.yaml"
        with open(output_file, "w") as f:
            yaml.safe_dump(
                log.model_dump(mode="json"),
                f,
                default_flow_style=False,
                sort_keys=False,
            )

        console.print(f"  ✓ Generated {output_file.name}")

    def generate_categories(self, categories: list[CategoryDefinition]) -> None:
        """Generate categories.yaml.

        Args:
            categories: Category definitions
        """
        output_data = CategoriesOutput(
            categories=categories,
            total_categories=len(categories),
            seed_categories=sum(1 for c in categories if c.is_seed),
            emerged_categories=sum(1 for c in categories if not c.is_seed),
        )

        output_file = self.output_dir / "categories.yaml"
        with open(output_file, "w") as f:
            yaml.safe_dump(
                output_data.model_dump(mode="json"),
                f,
                default_flow_style=False,
                sort_keys=False,
            )

        console.print(f"  ✓ Generated {output_file.name}")

    def generate_high_value_pages(self, pages: list[ConfluencePage]) -> None:
        """Generate high-value-pages.yaml.

        Args:
            pages: All extracted pages
        """
        high_value = [p for p in pages if p.value == PageValue.HIGH]

        # Sort by inbound links (descending)
        high_value.sort(key=lambda p: p.metadata.inbound_link_count, reverse=True)

        page_summaries = [
            {
                "page_id": p.metadata.page_id,
                "title": p.metadata.title,
                "url": p.metadata.url,
                "category": p.category.value if hasattr(p.category, 'value') else str(p.category),
                "inbound_links": p.metadata.inbound_link_count,
                "last_modified": p.metadata.last_modified.isoformat(),
                "value_reasoning": p.value_reasoning,
            }
            for p in high_value
        ]

        output_data = {
            "total_high_value_pages": len(high_value),
            "pages": page_summaries,
        }

        output_file = self.output_dir / "high-value-pages.yaml"
        with open(output_file, "w") as f:
            yaml.safe_dump(output_data, f, default_flow_style=False, sort_keys=False)

        console.print(f"  ✓ Generated {output_file.name} ({len(high_value)} pages)")

    def generate_triage_notes(
        self,
        pages: list[ConfluencePage],
        categories: list[CategoryDefinition],
    ) -> None:
        """Generate triage-notes.md.

        Args:
            pages: All extracted pages
            categories: Category definitions
        """
        # Gather statistics
        value_counts = {
            PageValue.HIGH: sum(1 for p in pages if p.value == PageValue.HIGH),
            PageValue.MEDIUM: sum(1 for p in pages if p.value == PageValue.MEDIUM),
            PageValue.LOW: sum(1 for p in pages if p.value == PageValue.LOW),
            PageValue.UNKNOWN: sum(1 for p in pages if p.value == PageValue.UNKNOWN),
        }

        category_counts: dict[str, int] = {}
        for page in pages:
            cat = page.category.value if hasattr(page.category, 'value') else str(page.category)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        emerged_categories = [c for c in categories if not c.is_seed]

        # Generate markdown
        lines = [
            "# Triage Notes - Phase 1 Consolidation\n",
            f"Generated: {datetime.utcnow().isoformat()}\n",
            "## Summary\n",
            f"- Total pages processed: {len(pages)}",
            f"- Successfully categorized: {sum(1 for p in pages if p.processed)}",
            f"- Total categories: {len(categories)} ({len(emerged_categories)} emerged during processing)\n",
            "## Value Distribution\n",
        ]

        for value, count in value_counts.items():
            percentage = (count / len(pages) * 100) if pages else 0
            lines.append(f"- **{value.value.upper()}**: {count} pages ({percentage:.1f}%)")

        lines.extend([
            "\n## Category Distribution\n",
        ])

        for cat_name, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(pages) * 100) if pages else 0
            lines.append(f"- **{cat_name}**: {count} pages ({percentage:.1f}%)")

        if emerged_categories:
            lines.extend([
                "\n## Emerged Categories\n",
                "New categories that emerged during processing:\n",
            ])
            for cat in emerged_categories:
                lines.extend([
                    f"### {cat.name}\n",
                    f"{cat.description}\n",
                    f"Pages: {cat.page_count}\n",
                ])

        lines.extend([
            "\n## Next Steps\n",
            "1. Review emerged categories - should they be merged with existing ones?",
            "2. Validate high-value page selections",
            "3. Identify pages that need human review (conflicting signals)",
            "4. Begin Phase 2: Knowledge Distillation for high-value pages\n",
        ])

        output_file = self.output_dir / "triage-notes.md"
        with open(output_file, "w") as f:
            f.write("\n".join(lines))

        console.print(f"  ✓ Generated {output_file.name}")
