"""Configuration management."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Confluence settings
    confluence_url: str = Field(..., description="Confluence instance URL")
    confluence_username: str = Field(..., description="Confluence username/email")
    confluence_api_token: str = Field(..., description="Confluence API token")
    confluence_space_key: str = Field(..., description="Space key to extract from")

    # Anthropic API settings
    anthropic_api_key: str = Field(..., description="Anthropic API key for LLM categorization")
    anthropic_model: str = Field(
        default="claude-sonnet-4-5-20251101",
        description="Anthropic model to use"
    )

    # Processing settings
    batch_size: int = Field(default=50, description="Pages to process before consolidation")
    max_pages: int = Field(default=0, description="Maximum pages to extract (0 for unlimited)")

    # Output settings
    output_dir: Path = Field(default=Path("data/outputs"), description="Output directory")
    raw_data_dir: Path = Field(default=Path("data/raw"), description="Raw data directory")
    processed_data_dir: Path = Field(default=Path("data/processed"), description="Processed data directory")

    class Config:
        """Pydantic settings configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def ensure_directories(self) -> None:
        """Create output directories if they don't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
