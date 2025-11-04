#!/bin/bash
# Stop clip server

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PID_FILE="$SCRIPT_DIR/server.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        echo "Clip server stopped (PID: $PID)"
        rm "$PID_FILE"
    else
        echo "Server not running (stale PID file)"
        rm "$PID_FILE"
    fi
else
    echo "Server PID file not found"
    # Try to find and kill any running clip_server.py
    pkill -f "clip_server.py" && echo "Killed clip_server.py process"
fi
