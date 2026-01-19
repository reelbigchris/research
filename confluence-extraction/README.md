# Confluence Knowledge Extraction

Extract and distill institutional knowledge from Confluence spaces into structured agent skills and developer onboarding documentation.

## Overview

This tool implements Phase 1 of the Confluence Knowledge Extraction plan:
- Connect to Confluence via API
- Extract pages with full metadata
- Perform initial categorization using LLM
- Triage content by value
- Generate structured outputs for further processing

## Installation

```bash
pip install -e .
```

For development:
```bash
pip install -e ".[dev]"
```

## Configuration

Create a `.env` file or set environment variables:

```bash
CONFLUENCE_URL=https://your-instance.atlassian.net
CONFLUENCE_USERNAME=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
CONFLUENCE_SPACE_KEY=YOUR_SPACE

ANTHROPIC_API_KEY=your-anthropic-api-key
```

## Usage

### Extract from Confluence

```bash
confluence-extract extract --space YOUR_SPACE
```

### Options

- `--space`: Confluence space key to extract from
- `--output-dir`: Directory for output files (default: ./data/outputs)
- `--batch-size`: Number of pages to process before consolidation checkpoint (default: 50)
- `--max-pages`: Maximum number of pages to extract (for testing)

## Output Structure

Phase 1 generates the following artifacts in `data/outputs/`:

- `extraction-log.yaml`: Record of all pages with metadata and categories
- `categories.yaml`: Canonical category list with definitions
- `high-value-pages.yaml`: Pages prioritized for synthesis
- `triage-notes.md`: Human observations and consolidation notes

## Project Structure

```
confluence-extraction/
├── src/confluence_extraction/
│   ├── api/              # Confluence API client
│   ├── models/           # Data models
│   ├── extraction/       # Page extraction logic
│   ├── categorization/   # LLM-based categorization
│   └── outputs/          # Output generation
├── tests/                # Test suite
├── config/               # Configuration templates
└── data/                 # Data directory
    ├── raw/              # Raw extracted content
    ├── processed/        # Processed/categorized content
    └── outputs/          # Final Phase 1 outputs
```

## Development

Run tests:
```bash
pytest
```

Format code:
```bash
black src/ tests/
ruff check src/ tests/
```

Type checking:
```bash
mypy src/
```
