#!/usr/bin/env bash
# Simple shell script — triggers run_shell panel in lmcode.

echo "=== system info ==="
python --version
echo "files in playground:"
ls -1 "$(dirname "$0")"
