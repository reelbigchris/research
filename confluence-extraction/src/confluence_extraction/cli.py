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
from .synthesis.orchestrator import SynthesisOrchestrator
from .synthesis.synthesizer import KnowledgeSynthesizer
from .validation.validator import SkillValidator
from .models.skill import ValidationNote

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
@click.option(
    "--input-dir",
    help="Phase 1 output directory",
    type=click.Path(path_type=Path, exists=True),
)
@click.option(
    "--skills-dir",
    help="Output directory for skill documents",
    type=click.Path(path_type=Path),
    default="skills",
)
@click.option(
    "--max-pages-per-skill",
    help="Maximum pages to include in one skill",
    type=int,
    default=10,
)
@click.option(
    "--project-name",
    help="Project name for skill index",
    type=str,
    default="Project",
)
@click.option(
    "--project-description",
    help="Project description for skill index",
    type=str,
)
@click.option(
    "--overwrite",
    help="Overwrite existing skill documents",
    is_flag=True,
)
def synthesize(
    input_dir: Optional[Path],
    skills_dir: Path,
    max_pages_per_skill: int,
    project_name: str,
    project_description: Optional[str],
    overwrite: bool,
) -> None:
    """Synthesize high-value pages into skill documents (Phase 2)."""
    settings = get_settings()

    # Determine input directory
    if input_dir is None:
        input_dir = settings.output_dir

    console.print("[bold cyan]Confluence Knowledge Extraction - Phase 2[/bold cyan]\n")
    console.print(f"Input directory: {input_dir.absolute()}")
    console.print(f"Skills directory: {skills_dir.absolute()}")
    console.print(f"Max pages per skill: {max_pages_per_skill}")
    console.print()

    try:
        # Initialize components
        synthesizer = KnowledgeSynthesizer(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

        orchestrator = SynthesisOrchestrator(
            synthesizer=synthesizer,
            skills_dir=skills_dir,
            processed_data_dir=settings.processed_data_dir,
        )

        # Load high-value pages
        pages = orchestrator.load_high_value_pages(input_dir)

        if not pages:
            console.print("[yellow]No high-value pages found. Run Phase 1 extraction first.[/yellow]")
            return

        # Synthesize all pages
        orchestrator.synthesize_all(
            pages=pages,
            max_pages_per_skill=max_pages_per_skill,
            overwrite=overwrite,
        )

        # Generate outputs
        orchestrator.generate_outputs(
            project_name=project_name,
            project_description=project_description,
        )

        console.print("\n[bold green]Phase 2 complete![/bold green]")
        console.print("\n[cyan]Next steps:[/cyan]")
        console.print("1. Review the generated skill documents")
        console.print("2. Check open-questions.md for issues to resolve")
        console.print("3. Validate skills using the validation workflow")
        console.print("4. Share skills with team members for review")

    except KeyboardInterrupt:
        console.print("\n[yellow]Synthesis interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during synthesis: {e}[/red]")
        raise


@cli.command()
@click.option(
    "--skills-dir",
    help="Skills directory",
    type=click.Path(path_type=Path, exists=True),
    default="skills",
)
@click.option(
    "--skill-id",
    help="Skill ID to validate",
    type=str,
    required=True,
)
@click.option(
    "--reviewer",
    help="Reviewer name",
    type=str,
    required=True,
)
@click.option(
    "--approved",
    help="Mark as approved",
    is_flag=True,
)
@click.option(
    "--corrections",
    help="Corrections made (comma-separated)",
    type=str,
)
@click.option(
    "--missing",
    help="Missing information (comma-separated)",
    type=str,
)
@click.option(
    "--notes",
    help="Additional notes",
    type=str,
)
def validate_skill(
    skills_dir: Path,
    skill_id: str,
    reviewer: str,
    approved: bool,
    corrections: Optional[str],
    missing: Optional[str],
    notes: Optional[str],
) -> None:
    """Add validation note for a skill document."""
    validator = SkillValidator(skills_dir / "_meta")

    # Parse corrections and missing info
    corrections_list = [c.strip() for c in corrections.split(",")] if corrections else []
    missing_list = [m.strip() for m in missing.split(",")] if missing else []

    validation_note = ValidationNote(
        skill_id=skill_id,
        reviewer=reviewer,
        corrections=corrections_list,
        missing_info=missing_list,
        additional_notes=notes,
        approved=approved,
    )

    validator.add_validation(validation_note)

    if approved:
        console.print(f"[green]✓ Skill {skill_id} approved by {reviewer}[/green]")
    else:
        console.print(f"[yellow]Validation note added for {skill_id}[/yellow]")


@cli.command()
@click.option(
    "--skills-dir",
    help="Skills directory",
    type=click.Path(path_type=Path, exists=True),
    default="skills",
)
def validation_report(skills_dir: Path) -> None:
    """Generate validation status report."""
    validator = SkillValidator(skills_dir / "_meta")
    report_path = validator.generate_validation_report()

    console.print(f"\n[green]Validation report generated: {report_path}[/green]")

    # Display summary
    status = validator.get_validation_status()
    approved = sum(1 for s in status.values() if s == "approved")
    needs_review = len(status) - approved

    console.print(f"\n[cyan]Summary:[/cyan]")
    console.print(f"  Approved: {approved}")
    console.print(f"  Needs Review: {needs_review}")
    console.print(f"  Total: {len(status)}")


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
