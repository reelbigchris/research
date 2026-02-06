#!/bin/bash
# Setup script

echo "Setting up onboarding orchestrator..."

# Make scripts executable
chmod +x orchestrator.sh
chmod +x scripts/*.sh
chmod +x scripts/*.py

# Create config from example
if [ ! -f "config/config.sh" ]; then
    cp config/config.example.sh config/config.sh
    echo "Created config/config.sh - please edit with your settings"
else
    echo "config/config.sh already exists"
fi

# Create initial workspace
mkdir -p workspace/{research,prompts,logs}
echo "Created workspace directories"

echo ""
echo "Next steps:"
echo "1. Edit config/config.sh with your paths and settings"
echo "2. Verify your access skills work:"
echo "   claude code --skill confluence-access 'List spaces'"
echo "   claude code --skill jira-access 'Find 5 recent issues'"
echo "   claude code --skill codebase-overview 'Show structure'"
echo "3. Run: ./orchestrator.sh"
