#!/bin/bash
# Run this script to download the required dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

mkdir -p "$LIB_DIR/marked"
mkdir -p "$LIB_DIR/highlight"

echo "Downloading marked.js..."
curl -sL "https://cdn.jsdelivr.net/npm/marked/marked.min.js" \
    -o "$LIB_DIR/marked/marked.min.js"

echo "Downloading highlight.js..."
curl -sL "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js" \
    -o "$LIB_DIR/highlight/highlight.min.js"

echo "Downloading highlight.js theme..."
curl -sL "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css" \
    -o "$LIB_DIR/highlight/github-dark.min.css"

echo ""
echo "Done! All dependencies downloaded to $LIB_DIR"
echo ""
echo "Folder structure:"
find "$LIB_DIR" -type f
