# Phase 2: Knowledge Distillation

This document describes Phase 2 of the Confluence Knowledge Extraction system: transforming high-value pages into coherent skill documents.

## Overview

Phase 2 takes the triaged output from Phase 1 and synthesizes high-value pages into structured skill documents that serve both human readers and AI agents.

## Goals

1. **Synthesize knowledge** - Create coherent explanations from multiple sources
2. **Capture uncertainty** - Explicitly flag contradictions, gaps, and ambiguities
3. **Enable validation** - Provide a workflow for human review and correction
4. **Track provenance** - Maintain links back to source materials

## Process

### 1. Load High-Value Pages

Phase 2 starts by loading pages marked as HIGH value in Phase 1:

```bash
confluence-extract synthesize --project-name "Your Project"
```

This reads from `data/raw/extracted_pages.json` and filters to HIGH-value pages.

### 2. Group by Category

Pages are grouped by their assigned category (architecture, decisions, operations, etc.).

### 3. Synthesize Each Category

For each category:

1. **Select pages** - Up to N pages per skill (default: 10)
2. **Call LLM** - Use Claude to synthesize content
3. **Extract open questions** - Identify contradictions, gaps, ambiguities
4. **Generate skill document** - Markdown with YAML frontmatter
5. **Write to file** - Organized by category hierarchy

If a category has too many pages, they're split into multiple skill documents.

### 4. Generate Outputs

- **Skill documents** - Individual .md files organized by category
- **SKILL.md** - Top-level index with navigation
- **open-questions.md** - Consolidated list of unresolved issues
- **synthesis-metadata.json** - Statistics and metadata

## Synthesis Prompt

The LLM is given:

- **Category context** - What type of knowledge this is
- **All source pages** - Title, metadata, content (up to 5000 chars each)
- **Synthesis guidelines** - Focus on understanding, flag uncertainty, identify gaps

The LLM produces:

- **Title** - Descriptive skill title
- **Content** - Markdown explanation with sections
- **Key concepts** - Important terms/ideas covered
- **Open questions** - Contradictions, gaps, stale info, ambiguities
- **Code locations** - Related code paths if mentioned
- **Related skills** - Suggested connected topics
- **Confidence score** - 0-1 estimate of accuracy

## Skill Document Format

Each skill is written as a Markdown file with YAML frontmatter:

```markdown
---
skill_id: architecture/telemetry-subsystem
title: Telemetry Subsystem Architecture
category: architecture
created_at: 2025-01-19T22:00:00Z
sources:
  - type: confluence
    id: "12345"
    title: "Telemetry Architecture Overview"
    url: "https://..."
  - type: confluence
    id: "67890"
    title: "Telemetry Data Format"
    url: "https://..."
key_concepts:
  - "Stream processing"
  - "Data normalization"
  - "Compression format"
code_locations:
  - "src/telemetry/"
  - "config/telemetry.yaml"
related_skills:
  - "decisions/adr-047-telemetry-format"
confidence_score: 0.85
open_questions_count: 2
---

## Overview

The telemetry subsystem handles real-time data collection and processing...

## Key Concepts

### Stream Processing

...

## How It Works

...

## Related Information

- See [Telemetry Format Decision](../decisions/adr-047-telemetry-format.md)
- Code: `src/telemetry/processor/`
```

## Open Questions

The system tracks four types of issues:

### Contradiction

Pages disagree on facts. Example:
- **Description**: "Deployment uses Jenkins" vs "Deployment uses GitLab CI"
- **Source Pages**: 12345, 67890
- **Evidence**: Quotes from both pages

### Gap

Missing or undocumented information. Example:
- **Description**: No documentation on failure recovery for telemetry service
- **Source Pages**: None
- **Evidence**: Multiple pages reference it but none explain it

### Staleness

References to outdated information. Example:
- **Description**: References to "the new authentication system" from 2019
- **Source Pages**: 34567
- **Evidence**: Quote mentioning "new auth system"

### Ambiguity

Inconsistent terminology or unclear meaning. Example:
- **Description**: "Widget" used inconsistently - sometimes UI, sometimes data model
- **Source Pages**: Multiple
- **Evidence**: Examples of conflicting usage

## Validation Workflow

After synthesis, skills should be reviewed by subject matter experts.

### Adding Validation Notes

```bash
# Review and approve
confluence-extract validate-skill \
  --skill-id "architecture/telemetry" \
  --reviewer "Chris" \
  --approved

# Review with corrections
confluence-extract validate-skill \
  --skill-id "operations/deployment" \
  --reviewer "Chris" \
  --corrections "Fixed deployment steps,Updated tool versions" \
  --missing "Need to document rollback procedure" \
  --notes "Overall good, but missing failure scenarios"
```

### Validation Reports

Generate a report of validation status:

```bash
confluence-extract validation-report
```

This produces `skills/_meta/validation-report.md` showing:
- Approved skills
- Skills needing review
- Recent validation activity
- Corrections and missing information

### Validation Data

All validations are tracked in `skills/_meta/validation-log.json`:

```json
{
  "architecture/telemetry": [
    {
      "reviewer": "Chris",
      "timestamp": "2025-01-19T22:30:00Z",
      "corrections": ["Fixed code references"],
      "missing_info": ["Need failure modes"],
      "approved": false
    },
    {
      "reviewer": "Chris",
      "timestamp": "2025-01-20T10:00:00Z",
      "corrections": [],
      "missing_info": [],
      "approved": true
    }
  ]
}
```

## Skill Hierarchy

Skills are organized in a hierarchy:

```
skills/
├── SKILL.md                      # Top-level index (router)
├── architecture/                 # System design
│   ├── SKILL.md                 # Category overview (optional)
│   ├── system-overview.md
│   └── telemetry-subsystem.md
├── decisions/                    # ADRs and decisions
│   ├── SKILL.md
│   └── key-decisions.md
├── operations/                   # Deployment and ops
│   ├── SKILL.md
│   ├── deployment-process.md
│   └── debugging-common-issues.md
├── domain/                       # Business domain
│   ├── SKILL.md
│   └── glossary.md
└── _meta/                        # Metadata
    ├── open-questions.md
    ├── synthesis-metadata.json
    └── validation-log.json
```

### The Top-Level SKILL.md

This acts as a router for AI agents:

- **Project overview** - One paragraph description
- **Key concepts** - Important terms to understand
- **Where to look** - Which skills to consult for different questions
- **Available skills** - Complete list organized by category

Example:

```markdown
# Your Project Knowledge

## What This Project Is
[One paragraph overview]

## Key Concepts
- **Telemetry**: Real-time data collection system
- **Widget**: Core data structure representing...

## Where to Look

| Question Type | Consult |
|--------------|---------|
| System architecture | [System Overview](architecture/system-overview.md) |
| Why decisions were made | [Key Decisions](decisions/key-decisions.md) |
| Deployment procedures | [Deployment Process](operations/deployment-process.md) |

## Available Skills

### Architecture
- [System Overview](architecture/system-overview.md)
- [Telemetry Subsystem](architecture/telemetry-subsystem.md)

...
```

## Customization

### Max Pages Per Skill

Control how many pages are synthesized into each skill:

```bash
confluence-extract synthesize --max-pages-per-skill 15
```

Lower numbers (5-8) create more focused skills. Higher numbers (15-20) create comprehensive overviews.

### Grouping Strategy

Currently uses simple chunking. Future enhancements could:
- Group by parent page hierarchy
- Use semantic similarity
- Cluster by topic modeling
- Manual grouping via configuration

### Synthesis Prompt Tuning

Edit `src/confluence_extraction/synthesis/synthesizer.py` to customize the LLM prompt:

- Adjust guidelines for your domain
- Change emphasis (e.g., more technical depth)
- Add specific instructions for your team's style

## Iterating on Skills

To regenerate skills after corrections:

```bash
# Regenerate all skills (overwrites)
confluence-extract synthesize --overwrite

# Regenerate specific category by deleting files
rm -rf skills/architecture/
confluence-extract synthesize
```

Skills track their sources, so you can trace back to original Confluence pages if needed.

## Integration with Phase 3 (Future)

Phase 3 would add:

1. **Code linking** - Map skills to actual code files
2. **Freshness monitoring** - Detect when source pages change
3. **Automated updates** - Regenerate affected skills when sources change
4. **Usage tracking** - See which skills are most accessed/useful

## Tips for Success

### 1. Review High-Value Pages First

Before running synthesis, check `data/outputs/high-value-pages.yaml`. Are the right pages selected? If not, adjust categorization or manually edit the list.

### 2. Start with One Category

Test synthesis on a single category:

```python
# Custom script
from confluence_extraction.synthesis.synthesizer import KnowledgeSynthesizer

synthesizer = KnowledgeSynthesizer(api_key="...")
# Synthesize just architecture pages
```

### 3. Use Open Questions as TODOs

`open-questions.md` is your action list. Assign questions to team members to resolve.

### 4. Validate Iteratively

Don't wait to validate all skills at once. Review and approve as they're created:

```bash
# Review one skill
confluence-extract validate-skill \
  --skill-id "architecture/auth" \
  --reviewer "Chris" \
  --approved
```

### 5. Share with New Team Members

The real test: can a new developer use these skills to understand the system? Have them read through and note what's missing or wrong.

## Troubleshooting

### "No high-value pages found"

Phase 1 didn't identify any HIGH-value pages. Check:
- Are pages actually linked to each other in Confluence?
- Review `data/outputs/extraction-log.yaml` to see value assessments
- Consider manually marking pages as high-value

### Synthesis is very slow

Each skill requires an LLM API call. For large spaces:
- Use `--max-pages-per-skill` to create smaller skills (fewer calls)
- Process categories one at a time
- The tool includes retry logic but respect API rate limits

### Skills are too generic

Adjust the synthesis prompt to request more depth:
- Ask for specific examples
- Request code references
- Emphasize technical detail over general explanations

### Open questions are overwhelming

This is actually good - it surfaces real knowledge gaps. To manage:
- Prioritize by type (contradictions > gaps > staleness)
- Assign to subject matter experts
- Resolve incrementally

### Skills don't match team's style

Edit the synthesis prompt in `synthesizer.py` to match your team's documentation standards.

## Next Steps

After Phase 2:

1. **Review all skills** - Quick pass for accuracy
2. **Resolve open questions** - Assign to team members
3. **Share with team** - Get feedback on usefulness
4. **Use for onboarding** - Test with new team member
5. **Iterate** - Improve based on feedback
