"""LLM-based knowledge synthesis."""

import json
from typing import Optional

import anthropic
from rich.console import Console
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models.page import ConfluencePage
from ..models.skill import (
    OpenQuestion,
    QuestionType,
    SkillDocument,
    SkillMetadata,
    SourceReference,
    SynthesisResult,
)

console = Console()


SYNTHESIS_PROMPT = """You are synthesizing knowledge from multiple Confluence pages into a coherent skill document.

This document will serve two purposes:
1. Help new developers understand how the system works
2. Provide AI agents with structured knowledge about the project

Category: {category}
Topic: {topic}

Source Pages:
{pages_summary}

Full Content:
{full_content}

Your task:
1. Synthesize the information into a clear, coherent explanation
2. Focus on WHY things work the way they do, not just WHAT they do
3. Flag contradictions explicitly - if pages disagree, note it
4. Identify gaps - what's missing or unclear in the documentation
5. Distinguish between "the docs say" and "this appears to be true"
6. Capture key concepts that are important to understand
7. Identify related code locations if mentioned

Output JSON with this structure:
{{
  "title": "Skill title",
  "content": "Markdown content of the skill document. Use ## for sections. Include:\n- Overview section\n- Key concepts section\n- How it works section\n- Related information section",
  "key_concepts": ["concept1", "concept2"],
  "open_questions": [
    {{
      "type": "contradiction|gap|staleness|ambiguity",
      "description": "What's unclear or contradictory",
      "evidence": "Relevant quotes or references",
      "source_pages": ["page_id1", "page_id2"]
    }}
  ],
  "code_locations": ["path/to/relevant/code"],
  "confidence": 0.0-1.0,
  "synthesis_notes": "Notes about the synthesis process, uncertainties, etc.",
  "related_skills": ["suggested related topics to cover"]
}}

Guidelines:
- Be concise but complete
- Prefer understanding over detail dumps
- Call out uncertainty explicitly
- Good skills say "the documentation is unclear on X" rather than guessing
- If pages contradict each other, describe both views
- Focus on knowledge that would help someone understand the system
"""


class KnowledgeSynthesizer:
    """Synthesize pages into skill documents using LLM."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20251101",
    ):
        """Initialize synthesizer.

        Args:
            api_key: Anthropic API key
            model: Model to use for synthesis
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _call_llm(self, prompt: str) -> dict:
        """Call Anthropic API with retry logic.

        Args:
            prompt: Prompt to send

        Returns:
            Parsed JSON response
        """
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text

        # Extract JSON from response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        return json.loads(response_text)

    def synthesize(
        self,
        pages: list[ConfluencePage],
        category: str,
        topic: Optional[str] = None,
        skill_id: Optional[str] = None,
    ) -> SynthesisResult:
        """Synthesize multiple pages into a skill document.

        Args:
            pages: Pages to synthesize
            category: Category for the skill
            topic: Optional topic/title hint
            skill_id: Optional skill ID (generated if not provided)

        Returns:
            SynthesisResult with skill document
        """
        if not pages:
            raise ValueError("No pages provided for synthesis")

        console.print(f"[cyan]Synthesizing {len(pages)} pages for category: {category}[/cyan]")

        # Prepare pages summary
        pages_summary = []
        for page in pages:
            summary = f"- **{page.metadata.title}** (ID: {page.metadata.page_id})"
            summary += f"\n  Last modified: {page.metadata.last_modified.strftime('%Y-%m-%d')}"
            summary += f"\n  Links: {page.metadata.inbound_link_count}"
            summary += f"\n  URL: {page.metadata.url}"
            pages_summary.append(summary)

        # Prepare full content (limit to avoid token limits)
        full_content_parts = []
        for page in pages:
            content = page.content_markdown or page.content_html[:5000]
            # Limit each page to 5000 chars
            if len(content) > 5000:
                content = content[:5000] + "\n\n[Content truncated...]"

            full_content_parts.append(
                f"### {page.metadata.title} (ID: {page.metadata.page_id})\n\n{content}\n\n---\n"
            )

        # Create prompt
        prompt = SYNTHESIS_PROMPT.format(
            category=category,
            topic=topic or "General",
            pages_summary="\n".join(pages_summary),
            full_content="\n".join(full_content_parts),
        )

        try:
            # Call LLM
            result = self._call_llm(prompt)

            # Generate skill ID if not provided
            if not skill_id:
                skill_id = self._generate_skill_id(category, result.get("title", "untitled"))

            # Parse open questions
            open_questions = []
            for q in result.get("open_questions", []):
                try:
                    question_type = QuestionType(q["type"].lower())
                except ValueError:
                    question_type = QuestionType.GAP

                open_questions.append(
                    OpenQuestion(
                        question_type=question_type,
                        description=q["description"],
                        source_pages=q.get("source_pages", []),
                        evidence=q.get("evidence"),
                    )
                )

            # Create source references
            sources = [
                SourceReference(
                    source_type="confluence",
                    source_id=page.metadata.page_id,
                    title=page.metadata.title,
                    url=page.metadata.url,
                )
                for page in pages
            ]

            # Create skill metadata
            metadata = SkillMetadata(
                skill_id=skill_id,
                title=result["title"],
                category=category,
                sources=sources,
                open_questions_count=len(open_questions),
                confidence_score=result.get("confidence", 0.5),
            )

            # Create skill document
            skill = SkillDocument(
                metadata=metadata,
                content=result["content"],
                open_questions=open_questions,
                key_concepts=result.get("key_concepts", []),
                related_skills=result.get("related_skills", []),
                code_locations=result.get("code_locations", []),
                synthesis_notes=result.get("synthesis_notes"),
            )

            return SynthesisResult(
                skill=skill,
                pages_synthesized=[p.metadata.page_id for p in pages],
                synthesis_confidence=result.get("confidence", 0.5),
                warnings=[],
            )

        except Exception as e:
            console.print(f"[red]Error synthesizing skill: {e}[/red]")
            raise

    def _generate_skill_id(self, category: str, title: str) -> str:
        """Generate a skill ID from category and title.

        Args:
            category: Skill category
            title: Skill title

        Returns:
            Skill ID
        """
        # Normalize title to kebab-case
        normalized = title.lower()
        normalized = "".join(c if c.isalnum() or c.isspace() else "" for c in normalized)
        normalized = "-".join(normalized.split())

        return f"{category}/{normalized}"

    def synthesize_by_category(
        self,
        pages_by_category: dict[str, list[ConfluencePage]],
        max_pages_per_skill: int = 10,
    ) -> list[SynthesisResult]:
        """Synthesize pages grouped by category.

        Args:
            pages_by_category: Pages grouped by category
            max_pages_per_skill: Maximum pages to include in one skill

        Returns:
            List of synthesis results
        """
        results = []

        for category, pages in pages_by_category.items():
            console.print(f"\n[bold cyan]Category: {category}[/bold cyan]")
            console.print(f"Pages: {len(pages)}")

            if not pages:
                continue

            # If too many pages, create multiple skills
            if len(pages) > max_pages_per_skill:
                console.print(
                    f"[yellow]Too many pages ({len(pages)}), splitting into multiple skills[/yellow]"
                )

                # Group related pages (e.g., by inbound links or parent hierarchy)
                page_groups = self._group_related_pages(pages, max_pages_per_skill)

                for i, group in enumerate(page_groups, 1):
                    console.print(f"  Synthesizing group {i}/{len(page_groups)}...")
                    try:
                        result = self.synthesize(
                            pages=group,
                            category=category,
                            topic=f"{category} - Part {i}",
                        )
                        results.append(result)
                    except Exception as e:
                        console.print(f"[red]  Failed: {e}[/red]")
                        continue
            else:
                # Synthesize all pages into one skill
                try:
                    result = self.synthesize(
                        pages=pages,
                        category=category,
                    )
                    results.append(result)
                except Exception as e:
                    console.print(f"[red]Failed: {e}[/red]")
                    continue

        return results

    def _group_related_pages(
        self,
        pages: list[ConfluencePage],
        max_per_group: int,
    ) -> list[list[ConfluencePage]]:
        """Group related pages together.

        Uses simple grouping by parent page or just chunks.

        Args:
            pages: Pages to group
            max_per_group: Maximum pages per group

        Returns:
            List of page groups
        """
        # Simple chunking for now
        # TODO: Could use more sophisticated grouping (by parent, by topic similarity, etc.)
        groups = []
        for i in range(0, len(pages), max_per_group):
            groups.append(pages[i : i + max_per_group])

        return groups
