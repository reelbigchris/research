#!/bin/bash
# Main orchestrator control loop

set -e

# Clean up background workers on exit/interrupt
cleanup_workers() {
    local PIDS=$(jobs -p 2>/dev/null)
    if [ -n "$PIDS" ]; then
        log "Cleaning up background workers..."
        kill $PIDS 2>/dev/null
        wait $PIDS 2>/dev/null
    fi
}
trap cleanup_workers EXIT INT TERM

# Load configuration
if [ -f "config/config.sh" ]; then
    source config/config.sh
else
    echo "Error: config/config.sh not found. Copy from config.example.sh"
    exit 1
fi

# Load library functions
source lib/utils.sh
source lib/phases.sh

# Initialize workspace
init_workspace

# Main control loop
ITERATION=0

log "Starting orchestration"

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    log "=== Iteration $ITERATION ==="

    # Read current phase
    PHASE=$(jq -r '.phase' "$STATE_FILE")
    log "Current phase: $PHASE"

    case $PHASE in
        survey)
            run_survey_phase
            ;;
        research)
            run_research_phase
            ;;
        validate)
            run_validation_phase
            ;;
        synthesize)
            run_synthesis_phase
            ;;
        complete)
            log "Orchestration complete!"
            log "Final skill: $OUTPUT_SKILL_DIR/SKILL.md"
            exit 0
            ;;
        failed)
            log "Orchestration failed. Check logs in $LOGS_DIR"
            exit 1
            ;;
        *)
            log "Unknown phase: $PHASE"
            update_state '.phase = "failed"'
            exit 1
            ;;
    esac

    # Brief pause between iterations
    sleep 2
done

log "Warning: Hit max iterations ($MAX_ITERATIONS) without completion"
log "Current state: $(cat $STATE_FILE)"
exit 1
