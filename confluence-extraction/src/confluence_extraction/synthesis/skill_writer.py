"""Write skill documents to files."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

from ..models.skill import OpenQuestion, SkillDocument

console = Console()


class SkillWriter:
    """Write skill documents to the skill hierarchy."""

    def __init__(self, skills_dir: Path):
        """Initialize skill writer.

        Args:
            skills_dir: Base directory for skills
        """
        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def write_skill(self, skill: SkillDocument, overwrite: bool = False) -> Path:
        """Write a skill document to file.

        Args:
            skill: Skill document to write
            overwrite: Whether to overwrite existing file

        Returns:
            Path to written file
        """
        # Determine file path
        skill_path = self._get_skill_path(skill.metadata.skill_id)
        skill_path.parent.mkdir(parents=True, exist_ok=True)

        if skill_path.exists() and not overwrite:
            console.print(f"[yellow]Skill already exists: {skill_path}[/yellow]")
            console.print("[yellow]Use --overwrite to replace it[/yellow]")
            return skill_path

        # Generate frontmatter
        frontmatter = self._generate_frontmatter(skill)

        # Combine frontmatter and content
        full_content = f"---\n{frontmatter}\n---\n\n{skill.content}"

        # Write to file
        with open(skill_path, "w") as f:
            f.write(full_content)

        console.print(f"[green]✓ Wrote skill: {skill_path}[/green]")
        return skill_path

    def write_open_questions(
        self,
        questions: list[OpenQuestion],
        output_file: Optional[Path] = None,
    ) -> Path:
        """Write open questions to a consolidated file.

        Args:
            questions: List of open questions
            output_file: Output file path (default: skills_dir/_meta/open-questions.md)

        Returns:
            Path to written file
        """
        if output_file is None:
            meta_dir = self.skills_dir / "_meta"
            meta_dir.mkdir(parents=True, exist_ok=True)
            output_file = meta_dir / "open-questions.md"

        lines = [
            "# Open Questions\n",
            f"Generated: {datetime.utcnow().isoformat()}\n",
            "These questions need to be answered to improve the skill documentation.\n",
        ]

        # Group by type
        by_type: dict[str, list[OpenQuestion]] = {}
        for q in questions:
            q_type = q.question_type.value
            if q_type not in by_type:
                by_type[q_type] = []
            by_type[q_type].append(q)

        # Write each type
        for q_type, type_questions in sorted(by_type.items()):
            lines.append(f"\n## {q_type.title()}\n")

            for q in type_questions:
                lines.append(f"### {q.description}\n")

                if q.source_pages:
                    lines.append(f"**Source Pages:** {', '.join(q.source_pages)}\n")

                if q.evidence:
                    lines.append("**Evidence:**\n")
                    lines.append(f"> {q.evidence}\n")

                if q.resolved:
                    lines.append(f"**✓ Resolved** by {q.resolved_by} on {q.resolved_at}\n")
                    if q.resolution:
                        lines.append(f"**Resolution:** {q.resolution}\n")
                else:
                    lines.append("**Status:** Unresolved\n")

                lines.append("\n---\n")

        with open(output_file, "w") as f:
            f.write("\n".join(lines))

        console.print(f"[green]✓ Wrote open questions: {output_file}[/green]")
        return output_file

    def write_skill_index(
        self,
        skills: list[SkillDocument],
        project_name: str = "Project",
        project_description: Optional[str] = None,
    ) -> Path:
        """Write top-level SKILL.md index.

        Args:
            skills: All skill documents
            project_name: Project name
            project_description: Project description

        Returns:
            Path to written file
        """
        index_path = self.skills_dir / "SKILL.md"

        # Group skills by category
        by_category: dict[str, list[SkillDocument]] = {}
        for skill in skills:
            category = skill.metadata.category
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(skill)

        # Generate content
        lines = [
            f"# {project_name} Knowledge\n",
        ]

        if project_description:
            lines.append(f"## What This Project Is\n\n{project_description}\n")

        lines.append("## Key Concepts\n")

        # Collect all key concepts
        all_concepts = set()
        for skill in skills:
            all_concepts.update(skill.key_concepts)

        for concept in sorted(all_concepts):
            lines.append(f"- **{concept}**")

        lines.append("\n## Where to Look\n")
        lines.append("| Question Type | Consult |")
        lines.append("|--------------|---------|")

        for category, cat_skills in sorted(by_category.items()):
            skill_links = ", ".join([f"[{s.metadata.title}]({s.metadata.skill_id}.md)" for s in cat_skills[:3]])
            lines.append(f"| {category.title()} | {skill_links} |")

        lines.append("\n## Available Skills\n")

        for category, cat_skills in sorted(by_category.items()):
            lines.append(f"\n### {category.title()}\n")
            for skill in cat_skills:
                rel_path = Path(skill.metadata.skill_id).with_suffix(".md")
                lines.append(f"- [{skill.metadata.title}]({rel_path})")

        lines.append("\n## Critical Context\n")
        lines.append("Review the individual skill documents for detailed information.")

        with open(index_path, "w") as f:
            f.write("\n".join(lines))

        console.print(f"[green]✓ Wrote skill index: {index_path}[/green]")
        return index_path

    def _get_skill_path(self, skill_id: str) -> Path:
        """Get file path for a skill ID.

        Args:
            skill_id: Skill ID (e.g., "architecture/telemetry")

        Returns:
            Path to skill file
        """
        return self.skills_dir / f"{skill_id}.md"

    def _generate_frontmatter(self, skill: SkillDocument) -> str:
        """Generate YAML frontmatter for a skill.

        Args:
            skill: Skill document

        Returns:
            YAML frontmatter string
        """
        frontmatter_data = {
            "skill_id": skill.metadata.skill_id,
            "title": skill.metadata.title,
            "category": skill.metadata.category,
            "created_at": skill.metadata.created_at.isoformat(),
            "sources": [
                {
                    "type": src.source_type,
                    "id": src.source_id,
                    "title": src.title,
                    "url": src.url,
                }
                for src in skill.metadata.sources
            ],
            "key_concepts": skill.key_concepts,
            "code_locations": skill.code_locations,
            "related_skills": skill.related_skills,
            "confidence_score": skill.metadata.confidence_score,
            "open_questions_count": skill.metadata.open_questions_count,
        }

        if skill.metadata.last_reviewed:
            frontmatter_data["last_reviewed"] = skill.metadata.last_reviewed.isoformat()
            frontmatter_data["reviewed_by"] = skill.metadata.reviewed_by

        return yaml.dump(frontmatter_data, default_flow_style=False, sort_keys=False)
