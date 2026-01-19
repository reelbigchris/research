"""Tests for data models."""

from datetime import datetime

import pytest

from confluence_extraction.models.page import (
    ConfluencePage,
    PageCategory,
    PageMetadata,
    PageValue,
)


def test_page_metadata_creation():
    """Test creating page metadata."""
    metadata = PageMetadata(
        page_id="12345",
        title="Test Page",
        space_key="TEST",
        last_modified=datetime.utcnow(),
        author="Test Author",
        url="https://example.com/wiki/12345",
        version=1,
    )

    assert metadata.page_id == "12345"
    assert metadata.title == "Test Page"
    assert metadata.inbound_link_count == 0


def test_confluence_page_defaults():
    """Test ConfluencePage default values."""
    metadata = PageMetadata(
        page_id="12345",
        title="Test Page",
        space_key="TEST",
        last_modified=datetime.utcnow(),
        author="Test Author",
        url="https://example.com/wiki/12345",
        version=1,
    )

    page = ConfluencePage(
        metadata=metadata,
        content_html="<p>Test content</p>",
    )

    assert page.category == PageCategory.UNCATEGORIZED
    assert page.value == PageValue.UNKNOWN
    assert page.processed is False


def test_page_category_enum():
    """Test PageCategory enum values."""
    assert PageCategory.ARCHITECTURE.value == "architecture"
    assert PageCategory.DECISIONS.value == "decisions"
    assert PageCategory.OPERATIONS.value == "operations"


def test_page_value_enum():
    """Test PageValue enum values."""
    assert PageValue.HIGH.value == "high"
    assert PageValue.MEDIUM.value == "medium"
    assert PageValue.LOW.value == "low"
    assert PageValue.UNKNOWN.value == "unknown"
