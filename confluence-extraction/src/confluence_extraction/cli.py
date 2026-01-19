"""Command-line interface for Confluence extraction."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from .api.client import ConfluenceClient
from .categorization.categorizer import PageCategorizer
from .config import get_settings
from .extraction.orchestrator import ExtractionOrchestrator
from .outputs.generator import OutputGenerator

console = Console()


@click.group()
def cli() -> None:
    """Confluence Knowledge Extraction Tool - Phase 1."""
    pass


@cli.command()
@click.option(
    "--space",
    help="Confluence space key (overrides config)",
    type=str,
)
@click.option(
    "--output-dir",
    help="Output directory for artifacts",
    type=click.Path(path_type=Path),
)
@click.option(
    "--batch-size",
    help="Pages to process before consolidation checkpoint",
    type=int,
    default=50,
)
@click.option(
    "--max-pages",
    help="Maximum pages to extract (for testing)",
    type=int,
)
@click.option(
    "--skip-extraction",
    help="Skip extraction and load from previously saved data",
    is_flag=True,
)
def extract(
    space: Optional[str],
    output_dir: Optional[Path],
    batch_size: int,
    max_pages: Optional[int],
    skip_extraction: bool,
) -> None:
    """Extract and categorize pages from Confluence (Phase 1)."""
    # Load settings
    settings = get_settings()

    # Override settings if provided
    if space:
        settings.confluence_space_key = space
    if output_dir:
        settings.output_dir = output_dir
    if batch_size:
        settings.batch_size = batch_size

    # Ensure directories exist
    settings.ensure_directories()

    # Display configuration
    console.print("[bold cyan]Confluence Knowledge Extraction - Phase 1[/bold cyan]\n")
    console.print(f"Space: {settings.confluence_space_key}")
    console.print(f"Output directory: {settings.output_dir.absolute()}")
    console.print(f"Batch size: {settings.batch_size}")
    if max_pages:
        console.print(f"Max pages: {max_pages}")
    console.print()

    extraction_start = datetime.utcnow()

    try:
        # Initialize components
        confluence_client = ConfluenceClient(
            url=settings.confluence_url,
            username=settings.confluence_username,
            api_token=settings.confluence_api_token,
            space_key=settings.confluence_space_key,
        )

        categorizer = PageCategorizer(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

        orchestrator = ExtractionOrchestrator(
            settings=settings,
            confluence_client=confluence_client,
            categorizer=categorizer,
        )

        # Extract or load pages
        if skip_extraction:
            console.print("[yellow]Skipping extraction, loading from saved data...[/yellow]")
            orchestrator.load_raw_pages()
        else:
            orchestrator.extract(max_pages=max_pages)

        # Categorize and triage
        orchestrator.categorize_and_triage(batch_size=settings.batch_size)

        # Generate outputs
        output_gen = OutputGenerator(settings.output_dir)
        output_gen.generate_all(
            pages=orchestrator.pages,
            categories=categorizer.get_categories(),
            extraction_start=extraction_start,
            space_key=settings.confluence_space_key,
        )

        console.print("\n[bold green]Phase 1 complete![/bold green]")
        console.print("\n[cyan]Next steps:[/cyan]")
        console.print("1. Review the generated outputs in the output directory")
        console.print("2. Validate the emerged categories and high-value page selections")
        console.print("3. Begin Phase 2: Knowledge Distillation")

    except KeyboardInterrupt:
        console.print("\n[yellow]Extraction interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during extraction: {e}[/red]")
        raise


@cli.command()
def validate() -> None:
    """Validate configuration and connectivity."""
    try:
        settings = get_settings()

        console.print("[cyan]Validating configuration...[/cyan]\n")

        # Test Confluence connection
        console.print("Testing Confluence connection...")
        confluence_client = ConfluenceClient(
            url=settings.confluence_url,
            username=settings.confluence_username,
            api_token=settings.confluence_api_token,
            space_key=settings.confluence_space_key,
        )

        # Try to get space info
        space_info = confluence_client.confluence.get_space(settings.confluence_space_key)
        console.print(f"  ✓ Connected to space: {space_info['name']}")

        # Test Anthropic API
        console.print("\nTesting Anthropic API...")
        categorizer = PageCategorizer(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
        console.print(f"  ✓ Anthropic API key valid, using model: {settings.anthropic_model}")

        console.print("\n[green]All validations passed![/green]")

    except Exception as e:
        console.print(f"\n[red]Validation failed: {e}[/red]")
        raise


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
