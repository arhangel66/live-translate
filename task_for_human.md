# Tasks for Human

## Done
- [x] Get Gladia API Key
- [x] Get LiveKit Cloud Credentials
- [x] Create .env.local file

---

## Next: Get API Keys for Streaming Voice Translation

### 1. OpenAI API Key (for translation)
- [ ] Go to https://platform.openai.com/api-keys
- [ ] Create new API key
- [ ] Add to `.env.local`: `OPENAI_API_KEY=sk-...`

**Cost:** GPT-4o-mini ~$0.15/1M tokens. 1 hour talking ≈ $0.01-0.05

### 2. Cartesia API Key (for TTS)
- [ ] Go to https://play.cartesia.ai/
- [ ] Sign up / Sign in
- [ ] Get API key from dashboard
- [ ] Add to `.env.local`: `CARTESIA_API_KEY=...`

**Cost:** Free tier available, then ~$0.15/1000 chars

---

## How to Run

```bash
uv run python agent.py console
```

---

## Target Architecture

```
Microphone
    ↓
Gladia STT (interim every ~300ms)
    ↓
Word Buffer (accumulate 3-5 words)
    ↓
GPT-4o-mini (streaming translation)
    ↓
Cartesia TTS (streaming audio)
    ↓
Headphones (hear translation in real-time)
```

Expected latency: **300-800ms** from speech to translated audio
