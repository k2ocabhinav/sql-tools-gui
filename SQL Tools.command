#!/bin/bash
# SQL Tools - Run Script for macOS
# Run this script to launch SQL Tools GUI

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Run the Python script
python3 "$SCRIPT_DIR/sql_tools.py"
