# Live Voice Translator

## Task
Build real-time voice translator: microphone → translation → headphones

## Architecture
```
Microphone → LiveKit Room → Agent (STT + Translation) → TTS → Audio Output
```

## Tech Stack
- **LiveKit Agents** - real-time voice pipeline framework
- **Gladia STT** - speech-to-text with built-in translation
- **OpenAI TTS** - text-to-speech for audio output
- **Python** - implementation language

## Key Features
- Real-time translation (en/ru/de → ru)
- Noise cancellation
- Echo cancellation
- Low latency (WebRTC-based)

## Implementation Plan
1. Setup LiveKit agent with Gladia STT
2. Configure translation pipeline
3. Add audio input/output handling
4. Test with real microphone

## References
- [LiveKit Agents Docs](https://docs.livekit.io/agents/)
- [Gladia STT Translation](https://docs.livekit.io/agents/models/stt/plugins/gladia)
- [LiveKit Python SDK](https://github.com/livekit/python-sdks)
- [Agent Starter - Python](https://github.com/livekit-examples/agent-starter-python)

## Notes
- Gladia supports multi-language input: `languages=["en", "ru", "de"]`
- Translation target: `translation_target_languages=["ru"]`
- Alternative: use speech-to-speech models (OpenAI Realtime API)
