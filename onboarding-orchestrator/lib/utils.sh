#!/bin/bash
# Utility functions

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

init_workspace() {
    mkdir -p "$WORKSPACE" "$RESEARCH_DIR" "$LOGS_DIR" "$WORKSPACE/results"

    # Initialize state if needed
    if [ ! -f "$STATE_FILE" ]; then
        cat > "$STATE_FILE" << EOF
{
    "phase": "survey",
    "tasks_completed": [],
    "tasks_pending": [],
    "iteration": 0,
    "last_update": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
        log "Initialized state file"
    else
        log "Resuming from existing state"
    fi
}

update_state() {
    local FILTER="$1"
    shift

    jq "$FILTER" "$@" "$STATE_FILE" > "$STATE_FILE.tmp"
    mv "$STATE_FILE.tmp" "$STATE_FILE"
}

# Run a claude agent in headless mode
# Args: PROMPT SKILLS LOG_FILE
run_claude_agent() {
    local PROMPT="$1"
    local SKILLS="$2"
    local LOG="$3"

    # Build command args
    local CMD=(claude -p "$PROMPT" --allowedTools "$ALLOWED_TOOLS")

    # TODO: claude -p does not currently support --skill.
    # Skills must be available in ~/.config/claude/skills/ and will be
    # picked up automatically. The SKILLS arg is reserved for when
    # headless skill selection is supported. For now, all skills in the
    # user's skill directory are available to all agents.
    # When supported, uncomment:
    # if [ -n "$SKILLS" ]; then
    #     CMD+=(--skill "$SKILLS")
    # fi

    "${CMD[@]}" 2>&1 | tee -a "$LOG"
}

# Run a single research task (designed to be called in a subshell via &)
# Writes result to $WORKSPACE/results/<basename>.result
# Args: TASK_JSON
run_research_task() {
    local TASK_JSON="$1"

    local TITLE=$(echo "$TASK_JSON" | jq -r '.title')
    local AGENT=$(echo "$TASK_JSON" | jq -r '.agent')
    local OUTPUT=$(echo "$TASK_JSON" | jq -r '.output')
    local QUESTIONS=$(echo "$TASK_JSON" | jq -r '.questions | join("\n- ")')
    local RESULT_FILE="$WORKSPACE/results/$(basename "$OUTPUT" .md).result"
    local LOG="$LOGS_DIR/research-$(basename "$OUTPUT" .md)-$(date +%s).log"

    log "Worker started: $TITLE (PID $$)" | tee -a "$LOG"

    # Build prompt from template
    local PROMPT=$(cat "$PROMPTS_DIR/02-research-template.txt")
    PROMPT="${PROMPT//\{title\}/$TITLE}"
    PROMPT="${PROMPT//\{questions\}/$QUESTIONS}"
    PROMPT="${PROMPT//\{output_file\}/$OUTPUT}"
    PROMPT="${PROMPT//\{WORKSPACE\}/$WORKSPACE}"

    # Run the agent
    run_claude_agent "$PROMPT" "$AGENT" "$LOG"

    # Check if output was created
    local OUTPUT_FILE="$RESEARCH_DIR/$(basename "$OUTPUT")"

    if [ -f "$OUTPUT_FILE" ]; then
        echo "success" > "$RESULT_FILE"
        log "Worker complete: $TITLE" | tee -a "$LOG"
    else
        echo "failed" > "$RESULT_FILE"
        log "Worker failed: $TITLE" | tee -a "$LOG"
    fi
}

# Poll background PIDs and return the first one that has exited
# Args: PID [PID ...]
# Prints the finished PID to stdout, returns 0
# Returns 1 if none have finished
poll_finished_pid() {
    for PID in "$@"; do
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "$PID"
            return 0
        fi
    done
    return 1
}
