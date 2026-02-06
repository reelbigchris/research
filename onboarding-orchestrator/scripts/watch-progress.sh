#!/bin/bash
# Watch orchestrator progress

WORKSPACE="${WORKSPACE:-./workspace}"

watch -n 5 "
echo '=== Phase ==='
jq -r '.phase' $WORKSPACE/state.json 2>/dev/null

echo ''
echo '=== Task Status ==='
jq -r '.tasks_pending[] | \"[\(.status)] \(.title)\" + (if .retries then \" (retries: \(.retries))\" else \"\" end)' $WORKSPACE/state.json 2>/dev/null

echo ''
echo '=== Summary ==='
echo -n 'Running: '; jq '[.tasks_pending[] | select(.status == \"running\")] | length' $WORKSPACE/state.json 2>/dev/null
echo -n 'Pending: '; jq '[.tasks_pending[] | select(.status == \"pending\")] | length' $WORKSPACE/state.json 2>/dev/null
echo -n 'Complete: '; jq '[.tasks_pending[] | select(.status == \"complete\")] | length' $WORKSPACE/state.json 2>/dev/null
echo -n 'Failed: '; jq '[.tasks_pending[] | select(.status == \"failed\" or .status == \"exhausted\")] | length' $WORKSPACE/state.json 2>/dev/null

echo ''
echo '=== Result Files ==='
ls -lt $WORKSPACE/results/*.result 2>/dev/null | head -10

echo ''
echo '=== Recent Logs ==='
tail -30 $WORKSPACE/logs/*.log 2>/dev/null | tail -30
"
