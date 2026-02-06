#!/bin/bash
# Orchestrator configuration
# Copy this to config/config.sh and customize

# Workspace directory (where all outputs go)
WORKSPACE="./workspace"
RESEARCH_DIR="$WORKSPACE/research"
PROMPTS_DIR="./prompts"
SCRIPTS_DIR="./scripts"
LOGS_DIR="$WORKSPACE/logs"
STATE_FILE="$WORKSPACE/state.json"

# Skills to use (must exist in ~/.config/claude/skills/)
CONFLUENCE_SKILL="confluence-access"
JIRA_SKILL="jira-access"
CODEBASE_SKILL="codebase-overview"

# Where to create the final skill
OUTPUT_SKILL_DIR="$HOME/.config/claude/skills/user/new-engineer-guide"

# Orchestrator behavior
MAX_ITERATIONS=50  # Max iterations before giving up
WORKER_SLOTS=4     # Concurrent research agents (orchestrator is just bash during research, not an LLM slot)
MAX_TASK_RETRIES=2 # Max retries per failed research task

# Tools to grant headless agents (comma-separated)
ALLOWED_TOOLS="Bash,Read,Write,Edit,Glob,Grep"

# Data source configuration
CONFLUENCE_SPACES="Team Docs,Engineering,Architecture"
JIRA_PROJECTS="PROJ,ENG"
CODEBASE_PATH="$HOME/work/my-project"
