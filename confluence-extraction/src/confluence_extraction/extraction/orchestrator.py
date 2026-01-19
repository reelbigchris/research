"""Orchestrate the extraction and categorization process."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress

from ..api.client import ConfluenceClient
from ..categorization.categorizer import PageCategorizer
from ..config import Settings
from ..models.page import ConfluencePage

console = Console()


class ExtractionOrchestrator:
    """Orchestrate the Phase 1 extraction process."""

    def __init__(
        self,
        settings: Settings,
        confluence_client: ConfluenceClient,
        categorizer: PageCategorizer,
    ):
        """Initialize orchestrator.

        Args:
            settings: Application settings
            confluence_client: Confluence API client
            categorizer: Page categorizer
        """
        self.settings = settings
        self.confluence = confluence_client
        self.categorizer = categorizer
        self.pages: list[ConfluencePage] = []

    def extract(self, max_pages: Optional[int] = None) -> list[ConfluencePage]:
        """Extract pages from Confluence.

        Args:
            max_pages: Maximum number of pages to extract

        Returns:
            List of extracted pages
        """
        console.print("[bold cyan]Phase 1: Extraction and Triage[/bold cyan]\n")

        # Extract pages
        self.pages = self.confluence.extract_all_pages(max_pages=max_pages)

        # Save raw extraction
        self._save_raw_pages()

        return self.pages

    def categorize_and_triage(self, batch_size: Optional[int] = None) -> None:
        """Categorize and triage all pages with batch consolidation.

        Args:
            batch_size: Number of pages to process before consolidation
        """
        if not self.pages:
            console.print("[red]No pages to categorize. Run extract() first.[/red]")
            return

        batch_size = batch_size or self.settings.batch_size
        total_pages = len(self.pages)
        batches = (total_pages + batch_size - 1) // batch_size

        console.print(f"\n[cyan]Processing {total_pages} pages in {batches} batches[/cyan]\n")

        with Progress(console=console) as progress:
            task = progress.add_task(
                "[cyan]Categorizing pages...",
                total=total_pages
            )

            for i, page in enumerate(self.pages, 1):
                # Categorize page
                self.pages[i - 1] = self.categorizer.categorize_page(page)

                progress.update(
                    task,
                    advance=1,
                    description=f"[cyan]Categorized: {page.metadata.title[:40]}..."
                )

                # Consolidation checkpoint
                if i % batch_size == 0 or i == total_pages:
                    batch_num = (i + batch_size - 1) // batch_size
                    console.print(f"\n[yellow]Consolidation checkpoint: Batch {batch_num}/{batches}[/yellow]")
                    self._consolidation_checkpoint(batch_num)

        console.print("\n[green]Categorization and triage complete![/green]")

    def _save_raw_pages(self) -> None:
        """Save raw extracted pages to JSON."""
        output_file = self.settings.raw_data_dir / "extracted_pages.json"

        pages_data = [page.model_dump(mode="json") for page in self.pages]

        with open(output_file, "w") as f:
            json.dump(pages_data, f, indent=2, default=str)

        console.print(f"[green]Saved raw pages to {output_file}[/green]")

    def _consolidation_checkpoint(self, batch_num: int) -> None:
        """Generate consolidation checkpoint report.

        Args:
            batch_num: Current batch number
        """
        # Count categories
        category_counts: dict[str, int] = {}
        for page in self.pages:
            if page.processed:
                cat = page.category.value if hasattr(page.category, 'value') else str(page.category)
                category_counts[cat] = category_counts.get(cat, 0) + 1

        # Count emerged categories
        all_categories = self.categorizer.get_categories()
        emerged = [cat for cat in all_categories if not cat.is_seed]

        console.print(f"  Processed: {sum(1 for p in self.pages if p.processed)}/{len(self.pages)} pages")
        console.print(f"  Categories stable: {len(category_counts)}")
        console.print(f"  New categories emerged: {len(emerged)}")

        if emerged:
            console.print("  New categories:")
            for cat in emerged:
                console.print(f"    - {cat.name}: {cat.description}")

        console.print()

    def load_raw_pages(self) -> None:
        """Load previously extracted pages from JSON."""
        input_file = self.settings.raw_data_dir / "extracted_pages.json"

        if not input_file.exists():
            console.print(f"[red]No raw pages found at {input_file}[/red]")
            return

        with open(input_file) as f:
            pages_data = json.load(f)

        self.pages = [ConfluencePage.model_validate(p) for p in pages_data]
        console.print(f"[green]Loaded {len(self.pages)} pages from {input_file}[/green]")
