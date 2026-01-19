# Usage Guide

## Quick Start

### 1. Install Dependencies

```bash
cd confluence-extraction
pip install -e .
```

### 2. Configure Credentials

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
CONFLUENCE_URL=https://your-company.atlassian.net
CONFLUENCE_USERNAME=your-email@company.com
CONFLUENCE_API_TOKEN=your-api-token
CONFLUENCE_SPACE_KEY=YOUR_SPACE

ANTHROPIC_API_KEY=your-anthropic-api-key
```

#### Getting Confluence API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a label and copy the token

#### Getting Anthropic API Key

1. Go to https://console.anthropic.com/
2. Navigate to API Keys
3. Create a new API key

### 3. Validate Configuration

Test your configuration before running extraction:

```bash
confluence-extract validate
```

### 4. Run Extraction

Extract and process pages from your Confluence space:

```bash
confluence-extract extract --space YOUR_SPACE
```

#### Options

- `--space`: Confluence space key (overrides .env value)
- `--output-dir`: Custom output directory (default: data/outputs)
- `--batch-size`: Pages to process before consolidation (default: 50)
- `--max-pages`: Limit number of pages for testing (e.g., `--max-pages 10`)
- `--skip-extraction`: Load previously extracted pages instead of fetching from Confluence

#### Example: Test Run

Process only 10 pages to test the system:

```bash
confluence-extract extract --space YOUR_SPACE --max-pages 10
```

#### Example: Resume Processing

If extraction was interrupted or you want to re-categorize:

```bash
confluence-extract extract --skip-extraction
```

This loads previously extracted pages and re-runs categorization.

## Understanding the Outputs

After extraction completes, you'll find these files in `data/outputs/`:

### extraction-log.yaml

Complete record of all processed pages with:
- Page ID, title, URL
- Assigned category
- Value assessment (HIGH/MEDIUM/LOW)
- Last modified date
- Inbound link count

### categories.yaml

Canonical list of all categories including:
- Seed categories (predefined)
- Emerged categories (discovered during processing)
- Description and page count for each

### high-value-pages.yaml

Pages identified as HIGH value, sorted by inbound links. These are the prime candidates for Phase 2 synthesis.

### triage-notes.md

Human-readable summary including:
- Value distribution statistics
- Category distribution
- Emerged categories with descriptions
- Recommended next steps

## Workflow

### Phase 1: Initial Extraction

1. **Extract pages** - Run `confluence-extract extract`
2. **Review outputs** - Examine the generated YAML and markdown files
3. **Validate categories** - Check if emerged categories make sense
4. **Assess high-value pages** - Verify the HIGH value pages are truly valuable

### Consolidation Checkpoints

During processing, you'll see consolidation checkpoints every N pages (default: 50). These show:
- Number of pages processed
- Category stability
- New categories that emerged

This helps you catch issues early rather than after processing thousands of pages.

### Iterating

If you need to adjust categorization logic:

1. Modify `src/confluence_extraction/categorization/categorizer.py`
2. Run with `--skip-extraction` to re-process existing pages
3. Compare outputs to previous run

## Advanced Usage

### Custom Batch Size

Process in smaller batches for more frequent checkpoints:

```bash
confluence-extract extract --batch-size 25
```

### Custom Output Directory

Save outputs to a specific location:

```bash
confluence-extract extract --output-dir /path/to/outputs
```

### Processing Large Spaces

For large Confluence spaces (1000+ pages):

1. **Test first**: Run with `--max-pages 100` to validate setup
2. **Monitor progress**: Watch for new categories emerging
3. **Plan for time**: Categorization uses LLM API calls, expect ~1-2 seconds per page
4. **Check API limits**: Anthropic API has rate limits; the tool includes retry logic

## Troubleshooting

### "Validation failed: CONFLUENCE_URL"

Your `.env` file is missing or incomplete. Copy from `.env.example` and fill in all values.

### "Error extracting page: 401 Unauthorized"

Your Confluence credentials are incorrect. Double-check:
- URL includes `https://` and correct domain
- Username is your email
- API token is valid (not password)

### "Anthropic API error: rate limit"

You've hit API rate limits. The tool will retry automatically, but for very large spaces you may need to:
- Reduce batch size
- Process in multiple runs with `--max-pages`
- Use a higher tier Anthropic API key

### Extraction is very slow

This is expected. Each page requires:
1. API call to Confluence for page data
2. API call for metadata
3. API call for inbound links
4. LLM call for categorization

For 1000 pages, expect 30-60 minutes total processing time.

### "No high-value pages found"

Check your Confluence space:
- Are pages actually linked to each other?
- Are there architectural docs with multiple references?
- Try reviewing the extraction-log.yaml to see how pages were categorized

The tool prioritizes pages with:
- Multiple inbound links (5+)
- Recent modification
- Content indicating architecture/decisions

## Data Structure

```
confluence-extraction/
├── data/
│   ├── raw/
│   │   └── extracted_pages.json     # Raw page data
│   ├── processed/                   # (Reserved for Phase 2)
│   └── outputs/
│       ├── extraction-log.yaml
│       ├── categories.yaml
│       ├── high-value-pages.yaml
│       └── triage-notes.md
```

### Raw Data

`extracted_pages.json` contains the complete page data including:
- Full HTML and Markdown content
- All metadata
- Categorization results

This file can be large (MB to GB depending on space size). It's saved so you can:
- Re-run categorization without re-fetching from Confluence
- Perform offline analysis
- Resume if processing is interrupted

## Next Steps

After Phase 1 completes:

1. **Review high-value-pages.yaml** - These are candidates for Phase 2 synthesis
2. **Validate categories** - Merge or rename emerged categories as needed
3. **Identify gaps** - Look for pages that should be HIGH but were rated MEDIUM/LOW
4. **Plan Phase 2** - Select which high-value pages to distill first

Phase 2 (Knowledge Distillation) will synthesize the high-value pages into coherent skill documents. That implementation is separate but builds on these Phase 1 outputs.
