"""LLM-based page categorization and triage."""

import json
from typing import Optional

import anthropic
from rich.console import Console
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models.category import CategoryDefinition
from ..models.page import ConfluencePage, PageCategory, PageValue

console = Console()


CATEGORIZATION_PROMPT = """You are analyzing Confluence pages to categorize them and assess their value for knowledge extraction.

Current category definitions:
{categories}

For the page below, determine:
1. Which category best fits (use existing categories if they fit, propose a new one if they don't)
2. The value of this page (HIGH, MEDIUM, or LOW) for knowledge extraction
3. Your reasoning for both decisions

Page Title: {title}
Last Modified: {last_modified}
Inbound Links: {inbound_links}
Parent: {parent}

Content Preview (first 3000 chars):
{content}

Respond with JSON in this exact format:
{{
  "category": "category_name",
  "category_reasoning": "why this category fits",
  "suggested_new_category": "new_category_name or null",
  "new_category_description": "description if suggesting new category, or null",
  "value": "HIGH, MEDIUM, or LOW",
  "value_reasoning": "explanation of value assessment"
}}

Value assessment guidelines:
- HIGH: Architecture docs, decision records, heavily referenced pages (5+ inbound links), content explaining "why"
- MEDIUM: Procedural docs, troubleshooting guides, integration specs, moderately referenced (2-4 links)
- LOW: Meeting notes, rarely referenced (0-1 links), unchanged for 3+ years, team roster/process pages
"""


class PageCategorizer:
    """Categorize and triage Confluence pages using LLM."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20251101",
    ):
        """Initialize categorizer.

        Args:
            api_key: Anthropic API key
            model: Model to use for categorization
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.categories: dict[str, CategoryDefinition] = self._initialize_categories()

    def _initialize_categories(self) -> dict[str, CategoryDefinition]:
        """Initialize seed categories."""
        seed_categories = {
            PageCategory.ARCHITECTURE.value: CategoryDefinition(
                name=PageCategory.ARCHITECTURE.value,
                description="System architecture, component design, technical diagrams",
                examples=["System overview", "Component architecture", "Data flow diagrams"],
                is_seed=True,
            ),
            PageCategory.DECISIONS.value: CategoryDefinition(
                name=PageCategory.DECISIONS.value,
                description="Architectural Decision Records (ADRs), key technical decisions, rationale",
                examples=["ADRs", "Technology choices", "Design decisions"],
                is_seed=True,
            ),
            PageCategory.OPERATIONS.value: CategoryDefinition(
                name=PageCategory.OPERATIONS.value,
                description="Deployment procedures, monitoring, operational runbooks",
                examples=["Deployment guide", "Monitoring setup", "Incident response"],
                is_seed=True,
            ),
            PageCategory.DOMAIN.value: CategoryDefinition(
                name=PageCategory.DOMAIN.value,
                description="Business domain concepts, terminology, domain model",
                examples=["Domain glossary", "Business concepts", "Domain model"],
                is_seed=True,
            ),
            PageCategory.TROUBLESHOOTING.value: CategoryDefinition(
                name=PageCategory.TROUBLESHOOTING.value,
                description="Debugging guides, common issues, troubleshooting procedures",
                examples=["Debug guide", "Common errors", "FAQ"],
                is_seed=True,
            ),
            PageCategory.INTEGRATION.value: CategoryDefinition(
                name=PageCategory.INTEGRATION.value,
                description="External system integrations, API documentation, integration specs",
                examples=["API docs", "External integrations", "Third-party services"],
                is_seed=True,
            ),
            PageCategory.TEAM_PROCESS.value: CategoryDefinition(
                name=PageCategory.TEAM_PROCESS.value,
                description="Team processes, workflows, development practices",
                examples=["Development workflow", "Code review process", "Team rituals"],
                is_seed=True,
            ),
            PageCategory.MEETING_NOTES.value: CategoryDefinition(
                name=PageCategory.MEETING_NOTES.value,
                description="Meeting notes, discussions, ephemeral content",
                examples=["Sprint planning", "Team meetings", "Discussion notes"],
                is_seed=True,
            ),
            PageCategory.OUTDATED.value: CategoryDefinition(
                name=PageCategory.OUTDATED.value,
                description="Deprecated information, obsolete documentation",
                examples=["Old architecture", "Deprecated features", "Historical notes"],
                is_seed=True,
            ),
        }
        return seed_categories

    def _format_categories(self) -> str:
        """Format current categories for prompt."""
        lines = []
        for cat in self.categories.values():
            lines.append(f"- {cat.name}: {cat.description}")
            if cat.examples:
                lines.append(f"  Examples: {', '.join(cat.examples)}")
        return "\n".join(lines)

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
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text

        # Extract JSON from response
        # Sometimes the model wraps it in markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        return json.loads(response_text)

    def categorize_page(self, page: ConfluencePage) -> ConfluencePage:
        """Categorize and triage a single page.

        Args:
            page: Page to categorize

        Returns:
            Updated page with categorization results
        """
        # Prepare content preview
        content_preview = (page.content_markdown or "")[:3000]

        prompt = CATEGORIZATION_PROMPT.format(
            categories=self._format_categories(),
            title=page.metadata.title,
            last_modified=page.metadata.last_modified.isoformat(),
            inbound_links=page.metadata.inbound_link_count,
            parent=page.metadata.parent_title or "None",
            content=content_preview,
        )

        try:
            result = self._call_llm(prompt)

            # Update page with results
            category_name = result["category"].lower().replace(" ", "_")

            # Check if it's a known category
            try:
                page.category = PageCategory(category_name)
            except ValueError:
                page.category = PageCategory.UNCATEGORIZED
                page.suggested_new_category = result.get("suggested_new_category")

                # Add new category if suggested
                if page.suggested_new_category:
                    self._add_category(
                        page.suggested_new_category,
                        result.get("new_category_description", ""),
                    )

            page.category_reasoning = result["category_reasoning"]

            # Set value
            value_str = result["value"].upper()
            page.value = PageValue(value_str.lower())
            page.value_reasoning = result["value_reasoning"]

            page.processed = True

            # Update category count
            if category_name in self.categories:
                self.categories[category_name].page_count += 1

        except Exception as e:
            console.print(f"[red]Error categorizing page {page.metadata.page_id}: {e}[/red]")
            page.category = PageCategory.UNCATEGORIZED
            page.value = PageValue.UNKNOWN
            page.processed = False

        return page

    def _add_category(self, name: str, description: str) -> None:
        """Add a new emerged category.

        Args:
            name: Category name
            description: Category description
        """
        normalized_name = name.lower().replace(" ", "_")

        if normalized_name not in self.categories:
            self.categories[normalized_name] = CategoryDefinition(
                name=normalized_name,
                description=description,
                examples=[],
                is_seed=False,
            )
            console.print(f"[yellow]New category emerged: {name}[/yellow]")

    def get_categories(self) -> list[CategoryDefinition]:
        """Get all current categories.

        Returns:
            List of category definitions
        """
        return list(self.categories.values())
