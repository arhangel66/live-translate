#!/bin/bash
# Stop all Live Translator services

echo "Stopping Live Translator..."

pkill -f "python agent.py" 2>/dev/null && echo "Agent stopped" || echo "Agent not running"
pkill -f "python server.py" 2>/dev/null && echo "Server stopped" || echo "Server not running"
pkill -f ngrok 2>/dev/null && echo "Ngrok stopped" || echo "Ngrok not running"

echo "Done"
