"""Models for Phase 1 outputs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .category import CategoryDefinition
from .page import PageValue


class PageSummary(BaseModel):
    """Summary of a page for output logs."""

    page_id: str
    title: str
    url: str
    category: str
    value: PageValue
    last_modified: datetime
    inbound_link_count: int


class ExtractionLog(BaseModel):
    """Complete log of extraction process."""

    extraction_started: datetime
    extraction_completed: Optional[datetime] = None
    space_key: str
    total_pages: int = 0
    processed_pages: int = 0
    pages: list[PageSummary] = Field(default_factory=list)


class TriageResult(BaseModel):
    """Results of triage process."""

    high_value_pages: list[PageSummary] = Field(default_factory=list)
    medium_value_pages: list[PageSummary] = Field(default_factory=list)
    low_value_pages: list[PageSummary] = Field(default_factory=list)

    category_distribution: dict[str, int] = Field(default_factory=dict)
    value_distribution: dict[str, int] = Field(default_factory=dict)

    new_categories_emerged: list[str] = Field(default_factory=list)
    consolidation_notes: list[str] = Field(default_factory=list)


class CategoriesOutput(BaseModel):
    """Output format for categories.yaml."""

    categories: list[CategoryDefinition]
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    total_categories: int = 0
    seed_categories: int = 0
    emerged_categories: int = 0
