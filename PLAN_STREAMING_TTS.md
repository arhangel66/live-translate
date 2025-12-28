# Plan: Streaming TTS on Interim Results

## Goal
Reduce translation latency by starting TTS before the user finishes speaking.

## Current Flow (problem)
```
User speaks ───────────────────────┐
                                   ▼
Gladia waits for silence ──────────┤ ~500-1500ms wait
                                   ▼
Final transcript + translation ────┤
                                   ▼
Cartesia TTS starts ───────────────┤ ~300-800ms
                                   ▼
Audio plays
```

**Total latency: 800-2300ms after user stops speaking**

## Proposed Flow (solution)
```
User speaks ───┬─ interim 1: "Привет" ──► LLM ──► "Hello" ──► TTS ──► Audio
               │
               ├─ interim 2: "Привет как" ──► LLM ──► "how" ──► TTS ──► Audio
               │
               ├─ interim 3: "Привет как дела" ──► LLM ──► "are you" ──► TTS
               │
               └─ final: Gladia translation ──► verify/complete
```

**Target latency: 300-500ms after first stable words**

---

## Critical Discovery: Gladia Interim Limitation

**Problem:** Gladia with `translation_enabled=True`:
- Interim results contain **ORIGINAL language** only
- Final result contains **translated text**

**Solution:** Use fast LLM (Gemini 3 Flash via OpenRouter) for interim translation.

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                     StreamingTranslator                      │
├─────────────────────────────────────────────────────────────┤
│  interim_history: list[str]     # Recent interim transcripts │
│  translated_cache: dict         # source -> translation      │
│  spoken_word_count: int         # Words already sent to TTS  │
│  speech_start_time: float       # For metrics                │
├─────────────────────────────────────────────────────────────┤
│  on_interim(text) ──► get_stable_prefix()                    │
│                   ──► translate_incremental()                │
│                   ──► session.say()                          │
│                                                              │
│  on_final(text)   ──► verify against Gladia translation      │
│                   ──► speak remaining / correct if needed    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   IncrementalTranslator                      │
├─────────────────────────────────────────────────────────────┤
│  OpenRouter API (Gemini 2.0 Flash - fastest ~800ms)          │
│  - Base URL: https://openrouter.ai/api/v1                    │
│  - Model: google/gemini-2.0-flash-001                        │
├─────────────────────────────────────────────────────────────┤
│  translate(source_text, context) -> new_words_only           │
│                                                              │
│  Prompt design:                                              │
│  - Short, focused on speed                                   │
│  - Includes previous translation for context                 │
│  - Returns ONLY new words (delta)                            │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```python
# Interim event received
interim = "Привет как дела"

# Step 1: Detect stable prefix (unchanged across last 2 interims)
stable_prefix = "Привет как"  # "дела" is too new

# Step 2: Check what we already translated
already_translated = "Hello how"  # from previous interim
already_spoken_count = 2  # ["Hello", "how"]

# Step 3: Translate only new stable words
new_source = "Привет как"  # Full stable prefix
# LLM returns: "Hello how" (full translation for context matching)
# We extract delta: [] (nothing new)

# Step 4: Next interim...
interim = "Привет как дела сегодня"
stable_prefix = "Привет как дела"  # "дела" is now stable
new_words_to_translate = "дела"
# LLM prompt includes context: "Previous: Привет как = Hello how"
# LLM returns: "are you" (just the new part)
# TTS: session.say("are you", allow_interruptions=True)
```

---

## Implementation Plan

### Phase 1: OpenRouter Integration
- [x] Research: OpenRouter API, Gemini 3 Flash
- [x] Add `openai` dependency (OpenRouter is OpenAI-compatible)
- [x] Create `IncrementalTranslator` class
- [x] Add `OPENROUTER_API_KEY` to .env
- [x] Model benchmark: **gemini-2.0-flash-001** is fastest (~800ms)

### Phase 2: Stable Word Detection
- [x] Research: Gladia interim behavior
- [x] Implement `get_stable_prefix()` - words unchanged in last 2 interims
- [x] Track `interim_history` in `StreamingTranslator`

### Phase 3: Incremental Translation
- [x] Design optimal prompt for speed + quality
- [x] Implement context-aware translation (pass previous translations)
- [x] Cache translations to avoid re-translating same prefix
- [x] Return only NEW words (delta) for TTS

### Phase 4: Wire Up TTS
- [x] Create `StreamingTranslator` class
- [x] Handle interim events → translate → TTS
- [x] Use `allow_interruptions=True` for interim speech
- [x] Track `spoken_word_count`

### Phase 5: Final Verification
- [x] On final: speak remaining words from Gladia translation
- [x] Strategy: don't interrupt, just complete the phrase

### Phase 6: Metrics & Tuning
- [x] Add "time to first audio" metric
- [x] Track LLM latency separately
- [ ] Track correction frequency
- [ ] Tune: stability threshold, min words for TTS

---

## LLM Prompt Design

### Option A: Minimal (fastest)
```
Translate to English. Only output the translation, nothing else.

Context: "Привет как" = "Hello how"
New text: "Привет как дела"
```

### Option B: Structured (more reliable)
```json
{"task": "translate_delta", "lang": "ru-en",
 "context": {"src": "Привет как", "tgt": "Hello how"},
 "new_src": "Привет как дела"}
```
Response: `{"delta": "are you"}`

### Option C: Few-shot (best quality)
```
You are a real-time interpreter. Translate incrementally.

Example:
Previous: "Я хочу" = "I want"
Current: "Я хочу пить"
Output: to drink

Now translate:
Previous: "{prev_src}" = "{prev_tgt}"
Current: "{current_src}"
Output:
```

**Recommendation:** Start with Option A for speed, switch to C if quality issues.

---

## Key Files to Modify

| File | Changes |
|------|---------|
| `agent.py` | Add StreamingTranslator, modify event handlers |
| `translator.py` | NEW: IncrementalTranslator class with OpenRouter |
| `.env.local` | Add OPENROUTER_API_KEY |
| `pyproject.toml` | Add openai dependency |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM latency too high | Use Gemini 3 Flash (fastest), short prompts |
| Translation quality | Include context, use few-shot if needed |
| Context drift | Verify against Gladia final translation |
| Rate limits | Cache translations, batch if needed |
| Cost | Gemini Flash is cheap ($0.50/M input) |

---

## Success Criteria

- [ ] Time-to-first-audio < 500ms (from first stable words)
- [ ] LLM translation latency < 200ms per request
- [ ] Mismatch rate with Gladia < 15%
- [ ] No audio glitches or overlapping speech
- [ ] Metrics visible in UI (including LLM latency)

---

## Implementation Order

1. **Add OpenRouter client** (IncrementalTranslator)
2. **Test translation quality** with sample phrases
3. **Add stable prefix detection** (log only, no TTS)
4. **Wire up incremental TTS** (with allow_interruptions=True)
5. **Add final verification** (compare with Gladia)
6. **Add metrics** (time_to_first_audio, llm_latency)
7. **Tune thresholds** based on testing

---

## Code Structure

```python
@dataclass
class StreamingTranslator:
    """Handles incremental translation with LLM and TTS."""

    translator: IncrementalTranslator
    interim_history: list[str] = field(default_factory=list)
    translated_prefix: str = ""
    spoken_word_count: int = 0
    speech_start_time: float | None = None
    first_audio_time: float | None = None

    def on_interim(self, text: str, session: AgentSession) -> None:
        """Process interim transcript: detect stable, translate, speak."""
        self.interim_history.append(text)

        stable = self.get_stable_prefix()
        if not stable:
            return

        # Translate new stable words
        new_translation = await self.translator.translate_delta(
            full_source=stable,
            previous_source=self.last_stable,
            previous_translation=self.translated_prefix
        )

        if new_translation:
            session.say(new_translation, allow_interruptions=True)
            self.spoken_word_count += len(new_translation.split())

    def on_final(self, text: str, session: AgentSession) -> None:
        """Handle final transcript from Gladia (with translation)."""
        # Gladia's final contains the official translation
        # Speak remaining words not yet spoken
        ...

    def get_stable_prefix(self) -> str:
        """Get words that haven't changed in last 2 interims."""
        ...

    def reset(self) -> None:
        """Reset state for new utterance."""
        ...


class IncrementalTranslator:
    """Fast LLM-based translator via OpenRouter."""

    def __init__(self, api_key: str, model: str = "google/gemini-3-flash-preview"):
        self.client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        self.model = model

    async def translate_delta(
        self,
        full_source: str,
        previous_source: str,
        previous_translation: str,
        target_lang: str = "en"
    ) -> str:
        """Translate only the new words, using context for consistency."""
        ...
```

---

## Approval Needed

Architecture looks good? Ready to implement?
