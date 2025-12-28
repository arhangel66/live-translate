# Live Voice Translator

Real-time voice translation between Russian and English using LiveKit, Gladia STT, and Cartesia TTS.

## Architecture

```
Microphone -> WebRTC -> Gladia STT (transcription + translation) -> Cartesia TTS -> Speakers
```

## Tech Stack

- **LiveKit Agents SDK** - real-time voice pipeline
- **Gladia** - speech-to-text with built-in translation
- **Cartesia** - text-to-speech (sonic-turbo model)
- **aiohttp** - token server for PWA

## Setup

1. Install dependencies:
```bash
uv sync
```

2. Copy environment template and fill in API keys:
```bash
cp .env.local.example .env.local
```

Required keys:
- `GLADIA_API_KEY` - from [gladia.io](https://gladia.io)
- `CARTESIA_API_KEY` - from [cartesia.ai](https://cartesia.ai)
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` - from [livekit.io](https://livekit.io)

## Run

Start all services (agent + server + ngrok):
```bash
./run.sh
```

Or run separately:
```bash
# Terminal 1: Agent
uv run python agent.py dev

# Terminal 2: Server
uv run python server.py

# Terminal 3: Ngrok (for mobile access)
ngrok http 8080
```

Open http://127.0.0.1:8080 in browser or use ngrok URL on mobile.

## Usage

1. Select translation direction (RU->EN or EN->RU)
2. Click "Connect"
3. Speak into microphone
4. Hear translation in headphones

## Project Structure

```
agent.py        - LiveKit agent with STT/TTS pipeline
server.py       - HTTP server for tokens and PWA
static/         - PWA frontend
run.sh          - Startup script
```
