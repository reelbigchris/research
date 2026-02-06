#!/bin/bash
# Phase execution functions

run_survey_phase() {
    local LOG="$LOGS_DIR/survey-$(date +%s).log"

    log "Running survey phase..." | tee -a "$LOG"

    # Inject config into prompt
    local PROMPT=$(cat "$PROMPTS_DIR/01-survey.txt")
    PROMPT="${PROMPT//\{CONFLUENCE_SPACES\}/$CONFLUENCE_SPACES}"
    PROMPT="${PROMPT//\{JIRA_PROJECTS\}/$JIRA_PROJECTS}"
    PROMPT="${PROMPT//\{CODEBASE_PATH\}/$CODEBASE_PATH}"
    PROMPT="${PROMPT//\{WORKSPACE\}/$WORKSPACE}"
    PROMPT="${PROMPT//\{WORKER_SLOTS\}/$WORKER_SLOTS}"

    # Run survey agent
    local SKILLS="$CONFLUENCE_SKILL,$JIRA_SKILL,$CODEBASE_SKILL"
    run_claude_agent "$PROMPT" "$SKILLS" "$LOG"

    # Check if research plan was created
    if [ -f "$WORKSPACE/research-plan.md" ]; then
        log "Research plan created"

        # Parse into tasks
        python3 "$SCRIPTS_DIR/parse-research-plan.py" \
            "$WORKSPACE/research-plan.md" \
            "$WORKSPACE/tasks.json"

        if [ -f "$WORKSPACE/tasks.json" ]; then
            # Update state with tasks
            update_state '.phase = "research" | .tasks_pending = $tasks' \
                --slurpfile tasks "$WORKSPACE/tasks.json"
            log "Parsed $(jq length $WORKSPACE/tasks.json) tasks"
        else
            log "Failed to parse research plan"
            update_state '.phase = "failed"'
        fi
    else
        log "Research plan not created"
        update_state '.phase = "failed"'
    fi
}

run_research_phase() {
    # Disable errexit for this function — we poll PIDs and handle failures manually
    set +e

    log "Running research phase with $WORKER_SLOTS worker slots..."

    mkdir -p "$WORKSPACE/results"

    # Build task queue from pending and failed-with-retries tasks
    local TASK_QUEUE=()
    local TASK_COUNT

    TASK_COUNT=$(jq '[.tasks_pending[] | select(.status == "pending" or .status == "failed")] | length' "$STATE_FILE")

    if [ "$TASK_COUNT" -eq 0 ]; then
        log "All research tasks complete"
        update_state '.phase = "validate"'
        set -e
        return
    fi

    log "$TASK_COUNT tasks to process"

    # Read tasks into queue array (one JSON blob per element)
    while IFS= read -r task_json; do
        TASK_QUEUE+=("$task_json")
    done < <(jq -c '.tasks_pending[] | select(.status == "pending" or .status == "failed")' "$STATE_FILE")

    # Track active workers: parallel arrays for PIDs and their task output names
    local WORKER_PIDS=()
    local WORKER_OUTPUTS=()
    local WORKER_TITLES=()
    local QUEUE_IDX=0
    local COMPLETED=0
    local FAILED=0

    # --- Helper: launch one task from the queue ---
    # Reads from QUEUE_IDX, appends to WORKER_PIDS/OUTPUTS/TITLES
    _launch_next_worker() {
        local TASK_JSON="${TASK_QUEUE[$QUEUE_IDX]}"
        local OUTPUT=$(echo "$TASK_JSON" | jq -r '.output')
        local TITLE=$(echo "$TASK_JSON" | jq -r '.title')
        QUEUE_IDX=$((QUEUE_IDX + 1))

        # Clear stale result file for this specific task
        rm -f "$WORKSPACE/results/$(basename "$OUTPUT" .md).result"

        # Mark as running in state
        update_state --arg out "$OUTPUT" \
            '(.tasks_pending[] | select(.output == $out) | .status) = "running"'

        log "Launching worker: $TITLE"

        # Launch in background subshell
        run_research_task "$TASK_JSON" &

        WORKER_PIDS+=($!)
        WORKER_OUTPUTS+=("$OUTPUT")
        WORKER_TITLES+=("$TITLE")
    }

    # Launch initial batch of workers (up to WORKER_SLOTS)
    while [ $QUEUE_IDX -lt ${#TASK_QUEUE[@]} ] && [ ${#WORKER_PIDS[@]} -lt $WORKER_SLOTS ]; do
        _launch_next_worker
    done

    log "${#WORKER_PIDS[@]} workers launched, $((${#TASK_QUEUE[@]} - QUEUE_IDX)) tasks queued"

    # Main pool loop: poll for completed workers, backfill from queue
    while [ ${#WORKER_PIDS[@]} -gt 0 ]; do
        local FOUND_FINISHED=false

        for i in "${!WORKER_PIDS[@]}"; do
            local PID="${WORKER_PIDS[$i]}"

            if ! kill -0 "$PID" 2>/dev/null; then
                # This worker has finished
                FOUND_FINISHED=true
                local FINISHED_OUTPUT="${WORKER_OUTPUTS[$i]}"
                local FINISHED_TITLE="${WORKER_TITLES[$i]}"
                local RESULT_FILE="$WORKSPACE/results/$(basename "$FINISHED_OUTPUT" .md).result"

                # Collect exit status (don't care about the code — we use result files)
                wait "$PID" 2>/dev/null || true

                # Read result file
                local RESULT="failed"
                if [ -f "$RESULT_FILE" ]; then
                    RESULT=$(cat "$RESULT_FILE")
                fi

                if [ "$RESULT" = "success" ]; then
                    log "Worker done (success): $FINISHED_TITLE"
                    COMPLETED=$((COMPLETED + 1))

                    update_state --arg out "$FINISHED_OUTPUT" \
                        '(.tasks_pending[] | select(.output == $out) | .status) = "complete"'
                else
                    log "Worker done (failed): $FINISHED_TITLE"
                    FAILED=$((FAILED + 1))

                    # Increment retry count, mark failed or exhausted
                    local RETRIES=$(jq -r --arg out "$FINISHED_OUTPUT" \
                        '.tasks_pending[] | select(.output == $out) | .retries // 0' "$STATE_FILE")

                    if [ "$RETRIES" -lt "$MAX_TASK_RETRIES" ]; then
                        update_state --arg out "$FINISHED_OUTPUT" \
                            '(.tasks_pending[] | select(.output == $out)) |= (.status = "failed" | .retries = ((.retries // 0) + 1))'
                        log "Will retry $FINISHED_TITLE (attempt $((RETRIES + 1))/$MAX_TASK_RETRIES)"
                    else
                        update_state --arg out "$FINISHED_OUTPUT" \
                            '(.tasks_pending[] | select(.output == $out) | .status) = "exhausted"'
                        log "Giving up on $FINISHED_TITLE after $MAX_TASK_RETRIES retries"
                    fi
                fi

                # Remove this worker from tracking arrays
                unset 'WORKER_PIDS[i]'
                unset 'WORKER_OUTPUTS[i]'
                unset 'WORKER_TITLES[i]'
                # Re-index arrays to remove gaps
                WORKER_PIDS=("${WORKER_PIDS[@]}")
                WORKER_OUTPUTS=("${WORKER_OUTPUTS[@]}")
                WORKER_TITLES=("${WORKER_TITLES[@]}")

                # Backfill: launch next queued task if available
                if [ $QUEUE_IDX -lt ${#TASK_QUEUE[@]} ]; then
                    _launch_next_worker
                fi

                # Only handle one completion per poll cycle to keep things orderly
                break
            fi
        done

        # If no worker finished this cycle, sleep briefly before polling again
        if [ "$FOUND_FINISHED" = false ]; then
            sleep 5
        fi
    done

    log "Research phase complete: $COMPLETED succeeded, $FAILED failed"

    # Re-enable errexit
    set -e

    # Check if there are failed tasks that can be retried
    local RETRYABLE=$(jq '[.tasks_pending[] | select(.status == "failed")] | length' "$STATE_FILE")

    if [ "$RETRYABLE" -gt 0 ]; then
        log "$RETRYABLE tasks can be retried, staying in research phase"
        # Stay in research phase — next iteration of main loop will re-enter
    else
        log "Moving to validation phase"
        update_state '.phase = "validate"'
    fi
}

run_validation_phase() {
    local LOG="$LOGS_DIR/validate-$(date +%s).log"

    log "Running validation phase..." | tee -a "$LOG"

    # Inject config
    local PROMPT=$(cat "$PROMPTS_DIR/03-validate.txt")
    PROMPT="${PROMPT//\{WORKSPACE\}/$WORKSPACE}"

    # Run validation agent
    local SKILLS="$CONFLUENCE_SKILL,$JIRA_SKILL,$CODEBASE_SKILL"
    run_claude_agent "$PROMPT" "$SKILLS" "$LOG"

    if [ -f "$WORKSPACE/validation-report.md" ]; then
        log "Validation complete"

        # Check if additional research needed
        if grep -q "Additional research needed" "$WORKSPACE/validation-report.md"; then
            log "Validation identified gaps, returning to research phase"
            update_state '.phase = "research"'
        else
            log "Validation passed, moving to synthesis"
            update_state '.phase = "synthesize"'
        fi
    else
        log "Validation failed"
        update_state '.phase = "failed"'
    fi
}

run_synthesis_phase() {
    local LOG="$LOGS_DIR/synthesize-$(date +%s).log"

    log "Running synthesis phase..." | tee -a "$LOG"

    # Create output skill directory
    mkdir -p "$OUTPUT_SKILL_DIR"

    # Inject config
    local PROMPT=$(cat "$PROMPTS_DIR/04-synthesize.txt")
    PROMPT="${PROMPT//\{WORKSPACE\}/$WORKSPACE}"
    PROMPT="${PROMPT//\{OUTPUT_SKILL_DIR\}/$OUTPUT_SKILL_DIR}"

    # Run synthesis agent
    local SKILLS="$CONFLUENCE_SKILL,$JIRA_SKILL,$CODEBASE_SKILL"
    run_claude_agent "$PROMPT" "$SKILLS" "$LOG"

    # Check result
    if [ -f "$OUTPUT_SKILL_DIR/SKILL.md" ]; then
        log "Skill created successfully!"
        log "Location: $OUTPUT_SKILL_DIR/SKILL.md"
        update_state '.phase = "complete"'
    else
        log "Synthesis failed"
        update_state '.phase = "failed"'
    fi
}
