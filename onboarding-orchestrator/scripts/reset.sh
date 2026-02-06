#!/bin/bash
# Reset workspace to start over

WORKSPACE="${WORKSPACE:-./workspace}"

read -p "Are you sure you want to reset the workspace? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

echo "Backing up existing workspace..."
if [ -d "$WORKSPACE" ]; then
    BACKUP="$WORKSPACE.backup.$(date +%s)"
    mv "$WORKSPACE" "$BACKUP"
    echo "Backup saved to: $BACKUP"
fi

echo "Creating fresh workspace..."
mkdir -p "$WORKSPACE"/{research,prompts,logs}

echo "Workspace reset complete"
