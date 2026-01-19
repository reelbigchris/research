#!/bin/bash
# Setup script for Confluence Extraction

set -e

echo "Setting up Confluence Knowledge Extraction..."

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oP '(?<=Python )\d+\.\d+' || echo "0.0")
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.10+ is required (found $python_version)"
    exit 1
fi

echo "✓ Python version: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install package
echo "Installing package and dependencies..."
pip install --upgrade pip
pip install -e .

echo "✓ Package installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env from example..."
    cp .env.example .env
    echo "✓ Created .env file - please edit it with your credentials"
    echo "  Edit .env and add:"
    echo "    - Confluence URL, username, API token, and space key"
    echo "    - Anthropic API key"
else
    echo "✓ .env file already exists"
fi

# Create data directories
mkdir -p data/{raw,processed,outputs}
echo "✓ Created data directories"

echo ""
echo "Setup complete! Next steps:"
echo ""
echo "1. Edit .env with your credentials:"
echo "   vim .env"
echo ""
echo "2. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Validate your configuration:"
echo "   confluence-extract validate"
echo ""
echo "4. Run extraction:"
echo "   confluence-extract extract --space YOUR_SPACE --max-pages 10"
echo ""
echo "See USAGE.md for detailed instructions."
