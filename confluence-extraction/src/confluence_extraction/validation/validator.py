"""Skill validation workflow."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..models.skill import SkillDocument, ValidationNote

console = Console()


class SkillValidator:
    """Manage skill validation workflow."""

    def __init__(self, validation_dir: Path):
        """Initialize validator.

        Args:
            validation_dir: Directory for validation data
        """
        self.validation_dir = validation_dir
        self.validation_dir.mkdir(parents=True, exist_ok=True)
        self.validation_file = validation_dir / "validation-log.json"

        # Load existing validations
        self.validations: dict[str, list[ValidationNote]] = {}
        if self.validation_file.exists():
            with open(self.validation_file) as f:
                data = json.load(f)
                for skill_id, notes in data.items():
                    self.validations[skill_id] = [
                        ValidationNote.model_validate(n) for n in notes
                    ]

    def add_validation(self, note: ValidationNote) -> None:
        """Add a validation note.

        Args:
            note: Validation note to add
        """
        if note.skill_id not in self.validations:
            self.validations[note.skill_id] = []

        self.validations[note.skill_id].append(note)
        self._save()

        console.print(f"[green]✓ Validation note added for {note.skill_id}[/green]")

    def get_validations(self, skill_id: str) -> list[ValidationNote]:
        """Get validation notes for a skill.

        Args:
            skill_id: Skill ID

        Returns:
            List of validation notes
        """
        return self.validations.get(skill_id, [])

    def is_approved(self, skill_id: str) -> bool:
        """Check if a skill is approved.

        Args:
            skill_id: Skill ID

        Returns:
            Whether the skill has been approved
        """
        notes = self.get_validations(skill_id)
        if not notes:
            return False

        # Check if the most recent validation is approved
        return notes[-1].approved

    def get_validation_status(self) -> dict[str, str]:
        """Get validation status for all skills.

        Returns:
            Dict mapping skill_id to status
        """
        status = {}
        for skill_id in self.validations:
            if self.is_approved(skill_id):
                status[skill_id] = "approved"
            else:
                status[skill_id] = "needs_review"

        return status

    def generate_validation_report(self, output_file: Optional[Path] = None) -> Path:
        """Generate a validation status report.

        Args:
            output_file: Output file path (default: validation_dir/validation-report.md)

        Returns:
            Path to report file
        """
        if output_file is None:
            output_file = self.validation_dir / "validation-report.md"

        lines = [
            "# Validation Report\n",
            f"Generated: {datetime.utcnow().isoformat()}\n",
        ]

        # Count statuses
        status = self.get_validation_status()
        approved_count = sum(1 for s in status.values() if s == "approved")
        needs_review_count = len(status) - approved_count

        lines.extend([
            "## Summary\n",
            f"- **Approved**: {approved_count}",
            f"- **Needs Review**: {needs_review_count}",
            f"- **Total**: {len(status)}\n",
        ])

        # List by status
        lines.append("## Skills by Status\n")

        lines.append("### Approved\n")
        for skill_id, s in status.items():
            if s == "approved":
                notes = self.get_validations(skill_id)
                last_note = notes[-1]
                lines.append(
                    f"- **{skill_id}** - Approved by {last_note.reviewer} "
                    f"on {last_note.timestamp.strftime('%Y-%m-%d')}"
                )

        lines.append("\n### Needs Review\n")
        for skill_id, s in status.items():
            if s == "needs_review":
                notes = self.get_validations(skill_id)
                if notes:
                    last_note = notes[-1]
                    lines.append(
                        f"- **{skill_id}** - Last reviewed by {last_note.reviewer} "
                        f"on {last_note.timestamp.strftime('%Y-%m-%d')}"
                    )
                else:
                    lines.append(f"- **{skill_id}** - Not yet reviewed")

        # Recent validations
        lines.append("\n## Recent Validations\n")

        all_notes = []
        for skill_id, notes in self.validations.items():
            for note in notes:
                all_notes.append((skill_id, note))

        # Sort by timestamp
        all_notes.sort(key=lambda x: x[1].timestamp, reverse=True)

        for skill_id, note in all_notes[:20]:  # Last 20
            status_str = "✓ Approved" if note.approved else "⚠ Needs changes"
            lines.append(
                f"- **{skill_id}** - {status_str} - {note.reviewer} "
                f"({note.timestamp.strftime('%Y-%m-%d')})"
            )

            if note.corrections:
                lines.append(f"  Corrections: {len(note.corrections)}")
            if note.missing_info:
                lines.append(f"  Missing info: {len(note.missing_info)}")

        with open(output_file, "w") as f:
            f.write("\n".join(lines))

        console.print(f"[green]✓ Generated validation report: {output_file}[/green]")
        return output_file

    def _save(self) -> None:
        """Save validations to file."""
        data = {
            skill_id: [note.model_dump(mode="json") for note in notes]
            for skill_id, notes in self.validations.items()
        }

        with open(self.validation_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
