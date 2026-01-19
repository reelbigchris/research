"""Confluence API client for extracting pages and metadata."""

from datetime import datetime
from typing import Optional

from atlassian import Confluence
from markdownify import markdownify as md
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..models.page import ConfluencePage, PageMetadata

console = Console()


class ConfluenceClient:
    """Client for interacting with Confluence API."""

    def __init__(
        self,
        url: str,
        username: str,
        api_token: str,
        space_key: str,
    ):
        """Initialize Confluence client.

        Args:
            url: Confluence instance URL
            username: Username or email
            api_token: API token
            space_key: Space key to work with
        """
        self.confluence = Confluence(
            url=url,
            username=username,
            password=api_token,
            cloud=True,
        )
        self.space_key = space_key
        self.url = url

    def get_all_pages(
        self,
        limit: Optional[int] = None,
        start: int = 0,
    ) -> list[str]:
        """Get all page IDs from the space.

        Args:
            limit: Maximum number of pages to retrieve (None for all)
            start: Starting index for pagination

        Returns:
            List of page IDs
        """
        console.print(f"[cyan]Fetching pages from space: {self.space_key}[/cyan]")

        page_ids = []
        batch_size = 100
        current_start = start

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching page list...", total=None)

            while True:
                results = self.confluence.get_all_pages_from_space(
                    space=self.space_key,
                    start=current_start,
                    limit=batch_size,
                    expand="",
                )

                if not results:
                    break

                batch_ids = [page["id"] for page in results]
                page_ids.extend(batch_ids)

                progress.update(task, description=f"Fetched {len(page_ids)} pages...")

                if len(results) < batch_size:
                    break

                if limit and len(page_ids) >= limit:
                    page_ids = page_ids[:limit]
                    break

                current_start += batch_size

        console.print(f"[green]Found {len(page_ids)} pages[/green]")
        return page_ids

    def get_page_metadata(self, page_id: str) -> PageMetadata:
        """Extract metadata for a page.

        Args:
            page_id: Confluence page ID

        Returns:
            PageMetadata object
        """
        # Get page with full metadata
        page = self.confluence.get_page_by_id(
            page_id=page_id,
            expand="version,ancestors,space,history,history.lastUpdated",
        )

        # Get inbound links
        inbound_links = self._get_inbound_links(page_id)

        # Extract parent information
        parent_id = None
        parent_title = None
        if page.get("ancestors"):
            parent = page["ancestors"][-1]  # Immediate parent
            parent_id = parent["id"]
            parent_title = parent["title"]

        # Parse dates
        last_modified = datetime.fromisoformat(
            page["version"]["when"].replace("Z", "+00:00")
        )

        # Get author and last modifier
        author = page["version"]["by"]["displayName"]
        last_modifier = page.get("history", {}).get("lastUpdated", {}).get("by", {}).get("displayName", author)

        return PageMetadata(
            page_id=page_id,
            title=page["title"],
            space_key=page["space"]["key"],
            last_modified=last_modified,
            author=author,
            last_modifier=last_modifier,
            parent_id=parent_id,
            parent_title=parent_title,
            inbound_links=inbound_links,
            inbound_link_count=len(inbound_links),
            url=f"{self.url}/wiki/spaces/{page['space']['key']}/pages/{page_id}",
            version=page["version"]["number"],
        )

    def get_page_content(self, page_id: str) -> tuple[str, str]:
        """Get page content in HTML and Markdown.

        Args:
            page_id: Confluence page ID

        Returns:
            Tuple of (html_content, markdown_content)
        """
        page = self.confluence.get_page_by_id(
            page_id=page_id,
            expand="body.storage",
        )

        html_content = page["body"]["storage"]["value"]
        markdown_content = md(html_content, heading_style="ATX")

        return html_content, markdown_content

    def extract_page(self, page_id: str) -> ConfluencePage:
        """Extract complete page with metadata and content.

        Args:
            page_id: Confluence page ID

        Returns:
            ConfluencePage object
        """
        metadata = self.get_page_metadata(page_id)
        html_content, markdown_content = self.get_page_content(page_id)

        return ConfluencePage(
            metadata=metadata,
            content_html=html_content,
            content_markdown=markdown_content,
        )

    def _get_inbound_links(self, page_id: str) -> list[str]:
        """Get IDs of pages that link to this page.

        Args:
            page_id: Confluence page ID

        Returns:
            List of page IDs that link to this page
        """
        try:
            # Use CQL to find pages linking to this page
            cql = f'link = "{page_id}"'
            results = self.confluence.cql(cql, limit=1000)

            if results and "results" in results:
                return [page["content"]["id"] for page in results["results"]]

            return []
        except Exception as e:
            console.print(f"[yellow]Warning: Could not fetch inbound links for {page_id}: {e}[/yellow]")
            return []

    def extract_all_pages(
        self,
        max_pages: Optional[int] = None,
    ) -> list[ConfluencePage]:
        """Extract all pages from the space.

        Args:
            max_pages: Maximum number of pages to extract (None for all)

        Returns:
            List of ConfluencePage objects
        """
        page_ids = self.get_all_pages(limit=max_pages)
        pages = []

        with Progress(console=console) as progress:
            task = progress.add_task(
                "[cyan]Extracting pages...",
                total=len(page_ids)
            )

            for page_id in page_ids:
                try:
                    page = self.extract_page(page_id)
                    pages.append(page)
                    progress.update(
                        task,
                        advance=1,
                        description=f"[cyan]Extracted: {page.metadata.title[:50]}..."
                    )
                except Exception as e:
                    console.print(f"[red]Error extracting page {page_id}: {e}[/red]")
                    progress.update(task, advance=1)
                    continue

        console.print(f"[green]Successfully extracted {len(pages)} pages[/green]")
        return pages
