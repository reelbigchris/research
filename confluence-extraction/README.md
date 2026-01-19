# Confluence Knowledge Extraction

Extract and distill institutional knowledge from Confluence spaces into structured agent skills and developer onboarding documentation.

## Overview

This tool implements a complete two-phase workflow for transforming Confluence content into actionable knowledge:

### Phase 1: Extraction and Triage
- Connect to Confluence via API
- Extract pages with full metadata
- Perform initial categorization using LLM
- Triage content by value (HIGH/MEDIUM/LOW)
- Generate structured outputs

### Phase 2: Knowledge Distillation
- Synthesize high-value pages into coherent skill documents
- Identify contradictions, gaps, and ambiguities
- Generate structured skills with source tracking
- Create validation workflow for human review
- Produce dual-purpose documentation (human + AI agent readable)

## Installation

```bash
pip install -e .
```

For development:
```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Setup
./setup.sh

# 2. Configure credentials
vim .env

# 3. Validate configuration
confluence-extract validate

# 4. Run Phase 1: Extract and categorize
confluence-extract extract --space YOUR_SPACE

# 5. Run Phase 2: Synthesize into skills
confluence-extract synthesize --project-name "Your Project"
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

### Phase 1: Extraction

Extract and categorize pages from Confluence:

```bash
# Full extraction
confluence-extract extract --space YOUR_SPACE

# Test with limited pages
confluence-extract extract --space YOUR_SPACE --max-pages 10

# Re-categorize existing data
confluence-extract extract --skip-extraction
```

**Options:**
- `--space`: Confluence space key
- `--output-dir`: Output directory (default: ./data/outputs)
- `--batch-size`: Checkpoint interval (default: 50)
- `--max-pages`: Limit pages for testing
- `--skip-extraction`: Re-process without re-fetching

### Phase 2: Synthesis

Synthesize high-value pages into skill documents:

```bash
# Basic synthesis
confluence-extract synthesize --project-name "Your Project"

# With description and custom output
confluence-extract synthesize \
  --project-name "Your Project" \
  --project-description "Brief project overview" \
  --skills-dir ./project-skills \
  --max-pages-per-skill 15

# Overwrite existing skills
confluence-extract synthesize --overwrite
```

**Options:**
- `--input-dir`: Phase 1 output directory
- `--skills-dir`: Output directory for skills (default: ./skills)
- `--max-pages-per-skill`: Max pages per skill (default: 10)
- `--project-name`: Project name for index
- `--project-description`: Project description
- `--overwrite`: Overwrite existing skills

### Validation Workflow

Add validation notes for reviewed skills:

```bash
# Approve a skill
confluence-extract validate-skill \
  --skill-id "architecture/telemetry" \
  --reviewer "Chris" \
  --approved

# Add corrections
confluence-extract validate-skill \
  --skill-id "architecture/auth" \
  --reviewer "Chris" \
  --corrections "Updated deployment section,Fixed code references" \
  --missing "Need to document failure modes"

# Generate validation report
confluence-extract validation-report
```

## Output Structure

### Phase 1 Outputs (`data/outputs/`)

- `extraction-log.yaml`: Complete record of all pages with metadata
- `categories.yaml`: Category definitions (seed + emerged)
- `high-value-pages.yaml`: HIGH-value pages for synthesis
- `triage-notes.md`: Human-readable summary and statistics

### Phase 2 Outputs (`skills/`)

```
skills/
├── SKILL.md                      # Top-level index
├── architecture/
│   ├── system-overview.md
│   └── telemetry-subsystem.md
├── decisions/
│   └── key-decisions.md
├── operations/
│   └── deployment-process.md
└── _meta/
    ├── open-questions.md         # Unresolved issues
    ├── synthesis-metadata.json   # Synthesis stats
    └── validation-log.json       # Validation tracking
```

Each skill document includes:
- YAML frontmatter with metadata and source tracking
- Synthesized content in Markdown
- Key concepts and code locations
- Related skills

## Project Structure

```
confluence-extraction/
├── src/confluence_extraction/
│   ├── api/              # Confluence API client
│   ├── models/           # Data models (Pydantic)
│   ├── extraction/       # Phase 1: Extraction logic
│   ├── categorization/   # LLM-based categorization
│   ├── synthesis/        # Phase 2: Knowledge synthesis
│   ├── validation/       # Validation workflow
│   ├── outputs/          # Output generation
│   ├── config.py         # Configuration
│   └── cli.py            # Command-line interface
├── tests/                # Test suite
├── data/                 # Data directory
│   ├── raw/              # Raw extracted pages
│   ├── processed/        # Processed data
│   └── outputs/          # Phase 1 outputs
├── skills/               # Phase 2 skill documents
├── docs/                 # Documentation
│   ├── USAGE.md          # Detailed usage guide
│   └── ARCHITECTURE.md   # Technical architecture
└── pyproject.toml        # Package configuration
```

## Documentation

- **[USAGE.md](USAGE.md)**: Detailed usage guide with examples and troubleshooting
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Technical architecture and design decisions

## Workflow

1. **Phase 1: Extraction** → Extract and categorize all pages
2. **Review Outputs** → Check high-value pages and categories
3. **Phase 2: Synthesis** → Generate skill documents
4. **Review Skills** → Check open questions and skill quality
5. **Validation** → Team reviews and approves skills
6. **Iterate** → Update skills based on feedback

## Key Features

✅ **Smart Extraction** - Full metadata, inbound links, hierarchy tracking
✅ **LLM Categorization** - Evolving categories with Claude
✅ **Value Triage** - Automatic HIGH/MEDIUM/LOW assessment
✅ **Knowledge Synthesis** - Coherent skills from multiple sources
✅ **Gap Detection** - Identifies contradictions and missing information
✅ **Source Tracking** - Full provenance from Confluence to skills
✅ **Validation Workflow** - Track review and approval status
✅ **Dual-Purpose Docs** - Human-readable + agent-usable

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

## License

MIT
