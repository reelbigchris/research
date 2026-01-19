"""Models for Confluence pages and metadata."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PageValue(str, Enum):
    """Page value classification for triage."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class PageCategory(str, Enum):
    """Initial seed categories for classification."""

    ARCHITECTURE = "architecture"
    DECISIONS = "decisions"
    OPERATIONS = "operations"
    DOMAIN = "domain"
    MEETING_NOTES = "meeting_notes"
    TEAM_PROCESS = "team_process"
    TROUBLESHOOTING = "troubleshooting"
    INTEGRATION = "integration"
    OUTDATED = "outdated"
    UNCATEGORIZED = "uncategorized"


class PageMetadata(BaseModel):
    """Metadata for a Confluence page."""

    page_id: str = Field(..., description="Confluence page ID")
    title: str = Field(..., description="Page title")
    space_key: str = Field(..., description="Space key")
    last_modified: datetime = Field(..., description="Last modification timestamp")
    author: str = Field(..., description="Page author/creator")
    last_modifier: Optional[str] = Field(None, description="Last person to modify the page")
    parent_id: Optional[str] = Field(None, description="Parent page ID")
    parent_title: Optional[str] = Field(None, description="Parent page title")
    inbound_links: list[str] = Field(default_factory=list, description="Page IDs linking to this page")
    inbound_link_count: int = Field(0, description="Number of inbound links")
    url: str = Field(..., description="Full URL to the page")
    version: int = Field(..., description="Page version number")


class ConfluencePage(BaseModel):
    """Complete Confluence page with content and metadata."""

    metadata: PageMetadata
    content_html: str = Field(..., description="Raw HTML content")
    content_markdown: Optional[str] = Field(None, description="Converted markdown content")

    # Categorization results (populated during processing)
    category: PageCategory = Field(PageCategory.UNCATEGORIZED, description="Assigned category")
    category_reasoning: Optional[str] = Field(None, description="Explanation for category assignment")
    suggested_new_category: Optional[str] = Field(None, description="Suggested new category if none fit well")

    # Triage results
    value: PageValue = Field(PageValue.UNKNOWN, description="Assessed value")
    value_reasoning: Optional[str] = Field(None, description="Explanation for value assessment")

    # Processing metadata
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="When this page was extracted")
    processed: bool = Field(False, description="Whether categorization/triage is complete")

    class Config:
        """Pydantic configuration."""
        use_enum_values = False
