#!/bin/bash
# Production Startup Script for BowlingMate Backend

# Kill any existing uvicorn process
pkill -f uvicorn

echo "Deploying BowlingMate Backend..."
source venv/bin/activate
export LOG_LEVEL=info

# Run in background with logging
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &

echo "Backend deployed in background (PID: $!)"
echo "Logs are being written to server.log"
echo "Health Check: http://localhost:8000/"
