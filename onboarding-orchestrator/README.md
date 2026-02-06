# Onboarding Orchestrator

Multi-agent system for generating comprehensive onboarding documentation from distributed institutional knowledge (Confluence, JIRA, git history, codebase).

## Overview

This orchestrator uses Claude Code to:
1. Survey existing documentation across multiple sources
2. Identify knowledge gaps
3. Delegate specialized research tasks to focused agents
4. Validate findings across sources
5. Synthesize into a comprehensive onboarding guide skill

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/build-with-claude/claude-code) installed
- Access skills configured:
  - `confluence-access` - How to query your Confluence
  - `jira-access` - How to query JIRA
  - `codebase-overview` - Overview of your codebase structure

## Quick Start

### 1. Configure

```bash
cp config/config.example.sh config/config.sh
# Edit config/config.sh with your paths and settings
```

### 2. Verify Access Skills

```bash
# Test that your access skills work
claude code --skill confluence-access "List all spaces"
claude code --skill jira-access "Find 5 recent issues"
claude code --skill codebase-overview "Show directory structure"
```

### 3. Run Orchestrator

```bash
./orchestrator.sh
```

### 4. Monitor Progress (optional)

```bash
# In a separate terminal
./scripts/watch-progress.sh
```

### 5. Review Results

```bash
# Check state
cat workspace/state.json

# View research outputs
ls -lh workspace/research/

# Read final skill
cat ~/.config/claude/skills/user/new-engineer-guide/SKILL.md
```

## How It Works

### Phase 1: Survey
- Orchestrator surveys Confluence, JIRA, and codebase
- Creates a research plan with specific tasks
- Identifies what exists vs. what's missing

### Phase 2: Research
- Spawns specialized agents for each research task
- Each agent investigates specific questions
- Outputs are saved to `workspace/research/`
- Sources are tracked and cited

### Phase 3: Validate
- Cross-checks findings across research outputs
- Identifies contradictions
- Verifies claims against original sources
- Flags low-confidence areas

### Phase 4: Synthesize
- Combines all research into coherent narrative
- Preserves source citations
- Creates final skill at `~/.config/claude/skills/user/new-engineer-guide/SKILL.md`

## Configuration

Edit `config/config.sh`:

```bash
# Workspace directory
WORKSPACE="./workspace"

# Skills to use
CONFLUENCE_SKILL="confluence-access"
JIRA_SKILL="jira-access"
CODEBASE_SKILL="codebase-overview"

# Output skill location
OUTPUT_SKILL_DIR="$HOME/.config/claude/skills/user/new-engineer-guide"

# Max iterations before giving up
MAX_ITERATIONS=50

# Confluence spaces to survey (comma-separated)
CONFLUENCE_SPACES="Team Docs,Engineering,Architecture"

# JIRA project keys (comma-separated)
JIRA_PROJECTS="PROJ,ENG"

# Codebase path
CODEBASE_PATH="$HOME/work/my-project"
```

## Troubleshooting

### Orchestrator gets stuck
- Check logs: `tail -f workspace/logs/*.log`
- Review state: `cat workspace/state.json`
- Manually advance phase: `jq '.phase = "research"' workspace/state.json > workspace/state.json.tmp && mv workspace/state.json.tmp workspace/state.json`

### Research task fails
- Check specific log in `workspace/logs/research-*.log`
- Review the task prompt in `workspace/prompts/research-task.txt`
- Manually run: `claude code --skill <skills> "$(cat workspace/prompts/research-task.txt)"`

### Access skills not working
- Verify skills exist: `ls ~/.config/claude/skills/user/`
- Test individually: `claude code --skill confluence-access "test"`
- Check skill documentation in the skill's SKILL.md file

### Starting over
```bash
./scripts/reset.sh
```

## Customization

### Adding New Research Tasks

Edit research plan during survey phase, or manually add to `workspace/research-plan.md`:

```markdown
### Task N: Your Custom Task
**Agent:** skill-name-1,skill-name-2
**Sources:** Specific pages, files, queries to investigate
**Output:** research/custom-task.md
**Questions:**
- What specific question?
- What context is needed?
```

### Changing Synthesis Structure

Edit `prompts/04-synthesize.txt` to change the final skill structure.

### Adding New Phases

1. Add phase function to `lib/phases.sh`
2. Add case to main loop in `orchestrator.sh`
3. Create prompt template in `prompts/`

## Architecture

```
+----------------------------------+
|  orchestrator.sh (control loop)  |
|  - Manages state                 |
|  - Runs phases                   |
|  - Handles retries               |
+----------------+-----------------+
                 |
        +--------+--------+
        v                 v
  +-----------+     +------------+
  |  Survey   |     |  Research  | (parallel tasks)
  |  Phase    |---->|  Phase     |
  +-----------+     +------+-----+
                           |
                           v
                    +------------+
                    |  Validate  |
                    |  Phase     |
                    +------+-----+
                           |
                           v
                    +--------------+
                    |  Synthesize  |
                    |  Phase       |
                    +--------------+
```

## File Outputs

- `workspace/state.json` - Current orchestrator state
- `workspace/research-plan.md` - Research plan from survey
- `workspace/tasks.json` - Parsed task list
- `workspace/research/*.md` - Individual research outputs
- `workspace/validation-report.md` - Validation findings
- `workspace/logs/*.log` - Execution logs
- `~/.config/claude/skills/user/new-engineer-guide/SKILL.md` - Final skill

## Contributing

This is a framework - customize it for your environment!

Common customizations:
- Additional data sources (GitLab, Notion, wikis, etc.)
- Different synthesis structures
- Custom validation rules
- Parallel research execution
- Integration with CI/CD

## License

MIT
