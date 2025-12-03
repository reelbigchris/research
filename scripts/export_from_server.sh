#!/bin/bash
#
# Export Ghidra projects from a Ghidra server to SQLite databases
#
# Usage:
#   ./export_from_server.sh <server> <repository> [output_dir] [options]
#
# Examples:
#   ./export_from_server.sh ghidra.company.com firmware-repo ./databases
#   ./export_from_server.sh ghidra.company.com firmware-repo ./databases --user admin
#   ./export_from_server.sh ghidra.company.com firmware-repo ./databases --keystore ~/.ghidra/keystore.p12
#
# Requirements:
#   - GHIDRA_INSTALL_DIR environment variable must be set
#   - For password auth: will prompt for password
#   - For PKI auth: use --keystore option
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for required environment
if [ -z "$GHIDRA_INSTALL_DIR" ]; then
    echo -e "${RED}Error: GHIDRA_INSTALL_DIR environment variable not set${NC}"
    echo "Please set it to your Ghidra installation directory"
    exit 1
fi

HEADLESS="$GHIDRA_INSTALL_DIR/support/analyzeHeadless"
if [ ! -f "$HEADLESS" ]; then
    echo -e "${RED}Error: analyzeHeadless not found at $HEADLESS${NC}"
    exit 1
fi

# Script directory (where export_to_sqlite.py lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT_SCRIPT="$SCRIPT_DIR/export_to_sqlite.py"

if [ ! -f "$EXPORT_SCRIPT" ]; then
    echo -e "${RED}Error: export_to_sqlite.py not found at $EXPORT_SCRIPT${NC}"
    exit 1
fi

# Parse arguments
SERVER=""
REPOSITORY=""
OUTPUT_DIR="./firmware-dbs"
USER_ID=""
KEYSTORE=""
PORT=""
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --user|-u)
            USER_ID="$2"
            shift 2
            ;;
        --keystore|-k)
            KEYSTORE="$2"
            shift 2
            ;;
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 <server> <repository> [output_dir] [options]"
            echo ""
            echo "Arguments:"
            echo "  server      Ghidra server hostname"
            echo "  repository  Repository name on the server"
            echo "  output_dir  Directory for output databases (default: ./firmware-dbs)"
            echo ""
            echo "Options:"
            echo "  --user, -u      User ID for server authentication"
            echo "  --keystore, -k  Path to keystore file for PKI auth"
            echo "  --port, -p      Server port (default: 13100)"
            echo "  --help, -h      Show this help"
            exit 0
            ;;
        -*)
            echo -e "${YELLOW}Warning: Unknown option $1${NC}"
            shift
            ;;
        *)
            if [ -z "$SERVER" ]; then
                SERVER="$1"
            elif [ -z "$REPOSITORY" ]; then
                REPOSITORY="$1"
            else
                OUTPUT_DIR="$1"
            fi
            shift
            ;;
    esac
done

# Validate required arguments
if [ -z "$SERVER" ] || [ -z "$REPOSITORY" ]; then
    echo -e "${RED}Error: Server and repository are required${NC}"
    echo "Usage: $0 <server> <repository> [output_dir] [options]"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build Ghidra URL
if [ -n "$PORT" ]; then
    GHIDRA_URL="ghidra://${SERVER}:${PORT}/${REPOSITORY}"
else
    GHIDRA_URL="ghidra://${SERVER}/${REPOSITORY}"
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Ghidra Server Export${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Server URL:  $GHIDRA_URL"
echo "Output dir:  $OUTPUT_DIR"
echo ""

# Build headless command arguments
HEADLESS_ARGS=()
HEADLESS_ARGS+=("$GHIDRA_URL")
HEADLESS_ARGS+=("-process")
HEADLESS_ARGS+=("-recursive")
HEADLESS_ARGS+=("-readOnly")
HEADLESS_ARGS+=("-noanalysis")

if [ -n "$USER_ID" ]; then
    HEADLESS_ARGS+=("-connect" "$USER_ID")
fi

if [ -n "$KEYSTORE" ]; then
    HEADLESS_ARGS+=("-keystore" "$KEYSTORE")
fi

# Use password prompt
HEADLESS_ARGS+=("-p")

# Create a temporary project directory for checkout
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT

echo -e "${YELLOW}Note: You may be prompted for your Ghidra server password${NC}"
echo ""

# First, list all programs in the repository
echo "Discovering programs in repository..."

# We'll use a simple script to list files
LIST_SCRIPT=$(mktemp)
cat > "$LIST_SCRIPT" << 'EOF'
# List all program files in the project
from ghidra.framework.model import DomainFile

def list_programs(folder, prefix=""):
    for file in folder.getFiles():
        print("PROGRAM:" + prefix + "/" + file.getName())
    for subfolder in folder.getFolders():
        list_programs(subfolder, prefix + "/" + subfolder.getName())

root = state.getProject().getProjectData().getRootFolder()
list_programs(root)
EOF

# This approach won't work directly - we need a different strategy
# Let's export each program as we process it

echo ""
echo -e "${GREEN}Starting export...${NC}"
echo "Each program will be exported to: $OUTPUT_DIR/<program_name>.db"
echo ""

# Create the actual export wrapper script
WRAPPER_SCRIPT=$(mktemp)
cat > "$WRAPPER_SCRIPT" << EOF
# Wrapper to export current program
import os
import sys

# Get the output directory from environment or use default
output_dir = os.environ.get('EXPORT_OUTPUT_DIR', './firmware-dbs')
program_name = currentProgram.getName()

# Sanitize program name for filename
safe_name = "".join(c if c.isalnum() or c in '-_.' else '_' for c in program_name)
output_path = os.path.join(output_dir, safe_name + '.db')

print("Exporting: %s -> %s" % (program_name, output_path))

# Now run the actual export script with this output path
# We need to set the args and run it
sys.argv = ['export_to_sqlite.py', output_path]
exec(open('$EXPORT_SCRIPT').read())
EOF

# Set environment variable for output directory
export EXPORT_OUTPUT_DIR="$OUTPUT_DIR"

# Run headless analyzer
echo "Running Ghidra headless analyzer..."
"$HEADLESS" "${HEADLESS_ARGS[@]}" -postScript "$WRAPPER_SCRIPT"

# Cleanup
rm -f "$LIST_SCRIPT" "$WRAPPER_SCRIPT"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Export complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Databases created in: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR"/*.db 2>/dev/null || echo "(No databases found - check for errors above)"
