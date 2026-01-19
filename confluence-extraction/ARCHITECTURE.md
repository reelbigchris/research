# Architecture Overview

## Project Structure

```
confluence-extraction/
├── src/confluence_extraction/      # Main package
│   ├── __init__.py
│   ├── config.py                   # Configuration management
│   ├── cli.py                      # Command-line interface
│   │
│   ├── api/                        # Confluence API client
│   │   ├── __init__.py
│   │   └── client.py               # ConfluenceClient class
│   │
│   ├── models/                     # Data models (Pydantic)
│   │   ├── __init__.py
│   │   ├── page.py                 # ConfluencePage, PageMetadata
│   │   ├── category.py             # Category definitions
│   │   └── outputs.py              # Output format models
│   │
│   ├── extraction/                 # Extraction orchestration
│   │   ├── __init__.py
│   │   └── orchestrator.py         # ExtractionOrchestrator
│   │
│   ├── categorization/             # LLM-based categorization
│   │   ├── __init__.py
│   │   └── categorizer.py          # PageCategorizer
│   │
│   └── outputs/                    # Output generation
│       ├── __init__.py
│       └── generator.py            # OutputGenerator
│
├── tests/                          # Test suite
│   ├── __init__.py
│   └── test_models.py
│
├── config/                         # Configuration templates
├── data/                           # Data directory
│   ├── raw/                        # Raw extracted pages
│   ├── processed/                  # Processed data (Phase 2)
│   └── outputs/                    # Phase 1 outputs
│
├── pyproject.toml                  # Package configuration
├── .env.example                    # Environment template
├── .gitignore
├── setup.sh                        # Setup script
├── README.md                       # Project overview
├── USAGE.md                        # Usage guide
└── ARCHITECTURE.md                 # This file
```

## Component Overview

### 1. Configuration (`config.py`)

Manages application settings using Pydantic Settings:
- Loads from environment variables and .env file
- Validates configuration
- Provides settings singleton

**Key class**: `Settings`

### 2. API Client (`api/client.py`)

Handles all interactions with Confluence API:
- Fetches page lists from space
- Extracts page content (HTML and Markdown)
- Retrieves metadata (author, dates, hierarchy)
- Finds inbound links using CQL

**Key class**: `ConfluenceClient`

**Key methods**:
- `get_all_pages()` - List all pages in space
- `extract_page()` - Get complete page with metadata
- `extract_all_pages()` - Extract all pages with progress tracking

### 3. Data Models (`models/`)

Pydantic models for type safety and validation:

**page.py**:
- `PageMetadata` - Page metadata (ID, title, dates, links, etc.)
- `ConfluencePage` - Complete page with content and categorization
- `PageCategory` - Category enum
- `PageValue` - Value assessment enum (HIGH/MEDIUM/LOW)

**category.py**:
- `CategoryDefinition` - Category with description and examples
- `Category` - Category assignment with confidence

**outputs.py**:
- `ExtractionLog` - Complete extraction record
- `TriageResult` - Triage statistics
- `CategoriesOutput` - Categories list output format

### 4. Categorization (`categorization/categorizer.py`)

Uses Anthropic's Claude to categorize and triage pages:
- Maintains evolving category list
- Starts with seed categories
- Allows new categories to emerge
- Assesses page value (HIGH/MEDIUM/LOW)

**Key class**: `PageCategorizer`

**Key methods**:
- `categorize_page()` - Categorize single page with LLM
- `get_categories()` - Get all current categories

**Prompt engineering**:
- Provides category definitions
- Includes page metadata and content preview
- Requests structured JSON response
- Allows category suggestions

### 5. Extraction Orchestrator (`extraction/orchestrator.py`)

Coordinates the overall Phase 1 process:
- Manages extraction flow
- Handles batch processing
- Provides consolidation checkpoints
- Saves/loads raw data

**Key class**: `ExtractionOrchestrator`

**Key methods**:
- `extract()` - Extract pages from Confluence
- `categorize_and_triage()` - Process pages in batches
- `load_raw_pages()` - Resume from saved data

### 6. Output Generator (`outputs/generator.py`)

Generates Phase 1 artifacts in YAML and Markdown:
- extraction-log.yaml
- categories.yaml
- high-value-pages.yaml
- triage-notes.md

**Key class**: `OutputGenerator`

### 7. CLI (`cli.py`)

Command-line interface using Click:
- `extract` command - Main extraction workflow
- `validate` command - Test configuration

## Data Flow

```
1. Configuration
   ↓
2. Confluence API → Extract Pages → Raw JSON
   ↓
3. LLM Categorization (batched)
   ↓
4. Consolidation Checkpoints
   ↓
5. Generate Phase 1 Outputs (YAML/MD)
```

## Key Design Decisions

### 1. Pydantic for Data Models

**Why**: Type safety, validation, easy JSON serialization

**Benefit**: Catches errors early, clear data contracts

### 2. Batch Processing with Checkpoints

**Why**: Large Confluence spaces have 1000+ pages

**Benefit**: Progress visibility, early issue detection

### 3. Evolving Category List

**Why**: Can't predict all categories up front

**Benefit**: Categories emerge naturally from content

### 4. Separate Extract and Categorize

**Why**: Confluence API calls are slow, LLM calls are expensive

**Benefit**: Can re-categorize without re-extracting

### 5. Rich Console Output

**Why**: Long-running process needs feedback

**Benefit**: Progress bars, colored output, clear status

## Extension Points

### Adding New Output Formats

Extend `OutputGenerator` with new methods. Follow the pattern:
```python
def generate_custom_output(self, pages: list[ConfluencePage]) -> None:
    # Generate output
    # Write to self.output_dir
```

### Custom Categorization Logic

Modify the prompt in `categorizer.py` or override `PageCategorizer`:
```python
class CustomCategorizer(PageCategorizer):
    def categorize_page(self, page: ConfluencePage) -> ConfluencePage:
        # Custom logic
        return page
```

### Adding Filters

Add filters to `ExtractionOrchestrator`:
```python
def extract(self, max_pages: Optional[int], filter_fn: Callable) -> list[ConfluencePage]:
    pages = self.confluence.extract_all_pages(max_pages)
    return [p for p in pages if filter_fn(p)]
```

## Phase 2 Integration

This Phase 1 implementation generates outputs designed for Phase 2:

- **high-value-pages.yaml** → Input for synthesis
- **categories.yaml** → Structure for skill organization
- **extraction-log.yaml** → Source tracking

Phase 2 will:
1. Read high-value pages
2. Synthesize into skill documents
3. Organize by category
4. Track sources back to Confluence

## Testing

Current test coverage focuses on data models. To extend:

```python
# tests/test_categorization.py
def test_categorizer_with_mock_api():
    # Mock Anthropic API
    # Test categorization logic

# tests/test_extraction.py
def test_orchestrator_batching():
    # Test batch processing
    # Verify checkpoint behavior
```

Use pytest fixtures for common test data:
```python
@pytest.fixture
def sample_page():
    return ConfluencePage(...)
```

## Performance Considerations

### API Rate Limits

- Confluence: ~100 requests/minute (typical)
- Anthropic: Varies by tier, includes retry logic with exponential backoff

### Memory Usage

- Raw pages stored in memory during processing
- For very large spaces (10,000+ pages), consider:
  - Processing in chunks
  - Streaming to disk
  - Batch categorization separately

### Optimization Opportunities

1. **Parallel Confluence API calls** - Currently sequential
2. **Batch LLM requests** - Anthropic supports batch API
3. **Caching category definitions** - Currently regenerated each call
4. **Incremental extraction** - Only fetch changed pages

## Error Handling

### Retry Logic

- Confluence API calls: No automatic retry (fails fast)
- Anthropic API calls: 3 retries with exponential backoff (tenacity)

### Graceful Degradation

- If categorization fails → page marked as UNCATEGORIZED
- If inbound link fetch fails → Warning logged, count = 0
- If page extraction fails → Skip page, continue with others

### Recovery

- Raw pages saved after extraction
- Can resume with `--skip-extraction`
- All outputs regenerated from saved data
