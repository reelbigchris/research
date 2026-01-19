"""Models for categories and category definitions."""

from typing import Optional

from pydantic import BaseModel, Field


class CategoryDefinition(BaseModel):
    """Definition of a category with examples."""

    name: str = Field(..., description="Category name")
    description: str = Field(..., description="What this category encompasses")
    examples: list[str] = Field(default_factory=list, description="Example page types")
    page_count: int = Field(0, description="Number of pages in this category")
    is_seed: bool = Field(True, description="Whether this was a seed category or emerged during processing")


class Category(BaseModel):
    """Category assignment for a page."""

    page_id: str
    category_name: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in assignment (0-1)")
    reasoning: Optional[str] = None
    suggested_new_category: Optional[str] = None
    suggested_category_description: Optional[str] = None
