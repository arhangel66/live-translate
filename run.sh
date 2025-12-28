#!/bin/bash
# Start all services for Live Translator

cd "$(dirname "$0")"

echo "Starting Live Translator..."

# Kill previous instances
pkill -f "python agent.py" 2>/dev/null
pkill -f "python server.py" 2>/dev/null
pkill -f ngrok 2>/dev/null

sleep 1

# Start agent
echo "[1/3] Starting agent..."
uv run python agent.py dev > /tmp/agent.log 2>&1 &

# Start server
echo "[2/3] Starting server..."
uv run python server.py > /tmp/server.log 2>&1 &

sleep 2

# Start ngrok
echo "[3/3] Starting ngrok..."
ngrok http 8080 > /tmp/ngrok.log 2>&1 &

sleep 3

# Get ngrok URL
URL=$(curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null)

echo ""
echo "================================"
echo "Local:  http://127.0.0.1:8080"
echo "iPhone: $URL"
echo "================================"
echo ""
echo "Logs:"
echo "  tail -f /tmp/agent.log"
echo "  tail -f /tmp/server.log"
echo ""
echo "Stop: pkill -f 'python agent.py|python server.py|ngrok'"
