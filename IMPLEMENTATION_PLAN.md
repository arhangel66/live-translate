# Streaming Voice Translation - Implementation Plan

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Microphone │ ──▶ │ Gladia STT  │ ──▶ │  Translator │ ──▶ │ Cartesia    │
│             │     │ (interim)   │     │  (GPT-4o)   │     │ TTS         │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                           │                   │                   │
                           ▼                   ▼                   ▼
                    "Привет как"      "Hello how"         🔊 Audio
                    "Привет как дела" "Hello how are you"
```

## Components

### 1. STT Stream (Gladia)
- Input: microphone audio
- Output: interim transcripts every ~300ms
- Config: `languages=["en", "ru"]`, `interim_results=True`, `translation_enabled=False`

### 2. Word Buffer
- Accumulates words from interim results
- Triggers translation every 3-5 words OR on punctuation (. ? !)
- Handles deduplication (interim may repeat words)

### 3. Translator (OpenAI GPT-4o-mini)
- Input: buffered text chunks
- Output: streaming translated text
- Prompt: "Translate to {target_lang}. Only output translation, nothing else."
- Detect source language → pick target (ru→en, en→ru)

### 4. TTS Stream (Cartesia)
- Input: translated text chunks
- Output: audio frames → headphones
- Voice: male, model "sonic-3"
- Streaming: `tts.stream()` + `push_text()`

## Data Flow

```python
# Pseudo-code
word_buffer = []
last_processed_text = ""

async def on_interim_transcript(text: str):
    # Extract new words (avoid duplicates)
    new_words = extract_new_words(text, last_processed_text)
    word_buffer.extend(new_words)

    # Trigger translation if buffer has 3+ words or punctuation
    if should_translate(word_buffer):
        chunk = " ".join(word_buffer)
        word_buffer.clear()

        # Translate via LLM (streaming)
        async for translated_chunk in translate(chunk):
            # Push to TTS (streaming)
            tts_stream.push_text(translated_chunk)

async def on_final_transcript(text: str):
    # Flush remaining buffer
    if word_buffer:
        chunk = " ".join(word_buffer)
        word_buffer.clear()
        async for translated_chunk in translate(chunk):
            tts_stream.push_text(translated_chunk)
```

## Files to Create/Modify

1. **agent.py** - main agent with full pipeline
2. **translator.py** - LLM translation logic
3. **.env.local** - add OPENAI_API_KEY, CARTESIA_API_KEY

## Dependencies to Add

```bash
uv add "livekit-agents[openai]~=1.2"
uv add "livekit-agents[cartesia]~=1.2"
```

## Edge Cases

1. **Language detection**: Use first interim to detect source language
2. **Overlap**: Don't start new TTS while previous is playing (queue or skip)
3. **Silence**: Reset buffer on long pause
4. **Error handling**: Graceful fallback if LLM/TTS fails

## Latency Budget

| Stage | Target | Notes |
|-------|--------|-------|
| STT interim | 300ms | Gladia sends every ~300ms |
| Word buffer | 0-500ms | Wait for 3-5 words |
| LLM TTFB | 200ms | GPT-4o-mini is fast |
| TTS TTFB | 100ms | Cartesia is very fast |
| **Total** | **600-1100ms** | From speech to audio |

## Testing Plan

1. Run in console mode
2. Speak Russian → hear English
3. Speak English → hear Russian
4. Measure actual latency
5. Tune word buffer size for best UX
