#!/bin/bash
# Start clip server in background

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OPENPILOT_DIR="$( cd "$SCRIPT_DIR/../.." && pwd )"

cd "$OPENPILOT_DIR"

# Activate virtual environment
source .venv/bin/activate

# Install Flask if not already installed
pip install flask > /dev/null 2>&1

# Start server
nohup python tools/clip/clip_server.py > tools/clip/server.log 2>&1 &
echo $! > tools/clip/server.pid

echo "Clip server started on http://localhost:8084"
echo "PID: $(cat tools/clip/server.pid)"
echo "Log: tools/clip/server.log"
echo ""
echo "To stop: kill \$(cat tools/clip/server.pid)"
