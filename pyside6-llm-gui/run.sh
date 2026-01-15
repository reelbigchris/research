#!/bin/bash
# Quick start script for the LLM Chat Interface

echo "Starting LLM Chat Interface..."
echo "==============================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies if needed
if ! python -c "import PySide6" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the application
echo "Launching chat interface..."
echo ""
python chat_app.py
