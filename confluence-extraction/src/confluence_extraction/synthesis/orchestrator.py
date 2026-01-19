"""Orchestrate Phase 2 synthesis process."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress

from ..models.page import ConfluencePage
from ..models.skill import OpenQuestion, SkillDocument
from .skill_writer import SkillWriter
from .synthesizer import KnowledgeSynthesizer

console = Console()


class SynthesisOrchestrator:
    """Orchestrate the Phase 2 knowledge synthesis process."""

    def __init__(
        self,
        synthesizer: KnowledgeSynthesizer,
        skills_dir: Path,
        processed_data_dir: Path,
    ):
        """Initialize orchestrator.

        Args:
            synthesizer: Knowledge synthesizer
            skills_dir: Directory for skill documents
            processed_data_dir: Directory for processed data
        """
        self.synthesizer = synthesizer
        self.skills_dir = skills_dir
        self.processed_data_dir = processed_data_dir
        self.skill_writer = SkillWriter(skills_dir)

        self.skills: list[SkillDocument] = []
        self.all_open_questions: list[OpenQuestion] = []

    def load_high_value_pages(self, extraction_output_dir: Path) -> list[ConfluencePage]:
        """Load high-value pages from Phase 1.

        Args:
            extraction_output_dir: Phase 1 output directory

        Returns:
            List of high-value pages
        """
        console.print("[cyan]Loading high-value pages from Phase 1...[/cyan]")

        # Load the extraction log to get page IDs
        import yaml

        high_value_file = extraction_output_dir.parent / "raw" / "extracted_pages.json"

        if not high_value_file.exists():
            raise FileNotFoundError(
                f"Could not find extracted pages at {high_value_file}. "
                "Run Phase 1 extraction first."
            )

        with open(high_value_file) as f:
            pages_data = json.load(f)

        # Filter to high-value pages
        high_value_pages = [
            ConfluencePage.model_validate(p)
            for p in pages_data
            if p.get("value") == "high"
        ]

        console.print(f"[green]Loaded {len(high_value_pages)} high-value pages[/green]")
        return high_value_pages

    def synthesize_all(
        self,
        pages: list[ConfluencePage],
        max_pages_per_skill: int = 10,
        overwrite: bool = False,
    ) -> None:
        """Synthesize all pages into skills.

        Args:
            pages: Pages to synthesize
            max_pages_per_skill: Maximum pages per skill document
            overwrite: Whether to overwrite existing skills
        """
        console.print("\n[bold cyan]Phase 2: Knowledge Distillation[/bold cyan]\n")

        # Group pages by category
        pages_by_category = self._group_by_category(pages)

        console.print(f"Found {len(pages_by_category)} categories to synthesize")

        with Progress(console=console) as progress:
            task = progress.add_task(
                "[cyan]Synthesizing skills...",
                total=len(pages_by_category)
            )

            for category, cat_pages in pages_by_category.items():
                progress.update(
                    task,
                    description=f"[cyan]Synthesizing: {category}..."
                )

                try:
                    # Synthesize category
                    results = self.synthesizer.synthesize_by_category(
                        {category: cat_pages},
                        max_pages_per_skill=max_pages_per_skill,
                    )

                    # Write skills
                    for result in results:
                        self.skills.append(result.skill)
                        self.all_open_questions.extend(result.skill.open_questions)

                        # Write skill document
                        self.skill_writer.write_skill(result.skill, overwrite=overwrite)

                except Exception as e:
                    console.print(f"[red]Error synthesizing {category}: {e}[/red]")

                progress.update(task, advance=1)

        console.print(f"\n[green]Synthesized {len(self.skills)} skill documents![/green]")

    def generate_outputs(
        self,
        project_name: str = "Project",
        project_description: Optional[str] = None,
    ) -> None:
        """Generate Phase 2 outputs.

        Args:
            project_name: Project name for index
            project_description: Project description
        """
        console.print("\n[cyan]Generating Phase 2 outputs...[/cyan]")

        # Write skill index
        self.skill_writer.write_skill_index(
            self.skills,
            project_name=project_name,
            project_description=project_description,
        )

        # Write open questions
        if self.all_open_questions:
            self.skill_writer.write_open_questions(self.all_open_questions)
            console.print(
                f"  Found {len(self.all_open_questions)} open questions across all skills"
            )

        # Save synthesis metadata
        self._save_synthesis_metadata()

        console.print("\n[green]Phase 2 outputs generated successfully![/green]")
        console.print(f"\n[cyan]Skills directory: {self.skills_dir.absolute()}[/cyan]")

    def _group_by_category(
        self,
        pages: list[ConfluencePage]
    ) -> dict[str, list[ConfluencePage]]:
        """Group pages by category.

        Args:
            pages: Pages to group

        Returns:
            Dict mapping category to pages
        """
        by_category: dict[str, list[ConfluencePage]] = {}

        for page in pages:
            category = page.category.value if hasattr(page.category, 'value') else str(page.category)

            if category not in by_category:
                by_category[category] = []

            by_category[category].append(page)

        return by_category

    def _save_synthesis_metadata(self) -> None:
        """Save synthesis metadata."""
        meta_dir = self.skills_dir / "_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)

        metadata_file = meta_dir / "synthesis-metadata.json"

        metadata = {
            "synthesis_date": datetime.utcnow().isoformat(),
            "total_skills": len(self.skills),
            "skills_by_category": {},
            "total_open_questions": len(self.all_open_questions),
            "open_questions_by_type": {},
            "skills": [
                {
                    "skill_id": skill.metadata.skill_id,
                    "title": skill.metadata.title,
                    "category": skill.metadata.category,
                    "confidence": skill.metadata.confidence_score,
                    "sources_count": len(skill.metadata.sources),
                    "open_questions_count": skill.metadata.open_questions_count,
                }
                for skill in self.skills
            ],
        }

        # Count by category
        for skill in self.skills:
            cat = skill.metadata.category
            metadata["skills_by_category"][cat] = metadata["skills_by_category"].get(cat, 0) + 1

        # Count questions by type
        for q in self.all_open_questions:
            q_type = q.question_type.value
            metadata["open_questions_by_type"][q_type] = (
                metadata["open_questions_by_type"].get(q_type, 0) + 1
            )

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        console.print(f"  ✓ Saved synthesis metadata")
