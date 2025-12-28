"""
Incremental Translator using OpenRouter API.

Translates text incrementally for streaming TTS, using context
from previous translations to maintain consistency.
"""

import os
import time
from dataclasses import dataclass, field

import openai


@dataclass
class TranslationResult:
    """Result of incremental translation."""

    delta: str  # New words to speak
    full_translation: str  # Full translation so far
    latency_ms: float  # LLM request latency


class IncrementalTranslator:
    """Fast LLM-based translator via OpenRouter."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "google/gemini-2.0-flash-001",
    ) -> None:
        self.client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.getenv("OPENROUTER_API_KEY"),
        )
        self.model = model

    async def translate_delta(
        self,
        current_source: str,
        previous_source: str = "",
        previous_translation: str = "",
        source_lang: str = "Russian",
        target_lang: str = "English",
    ) -> TranslationResult:
        """
        Translate incrementally, returning only new words.

        Args:
            current_source: Full source text to translate
            previous_source: Previously translated source text
            previous_translation: Translation of previous_source
            source_lang: Source language name
            target_lang: Target language name

        Returns:
            TranslationResult with delta (new words) and full translation
        """
        start = time.time()

        # Build prompt
        if previous_source and previous_translation:
            prompt = (
                f"Translate from {source_lang} to {target_lang}. "
                f"Output ONLY the translation, nothing else.\n\n"
                f"Context: \"{previous_source}\" = \"{previous_translation}\"\n"
                f"Full text: \"{current_source}\""
            )
        else:
            prompt = (
                f"Translate from {source_lang} to {target_lang}. "
                f"Output ONLY the translation, nothing else.\n\n"
                f"Text: \"{current_source}\""
            )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )

        latency_ms = (time.time() - start) * 1000
        full_translation = response.choices[0].message.content.strip()

        # Remove quotes if LLM added them
        if full_translation.startswith('"') and full_translation.endswith('"'):
            full_translation = full_translation[1:-1]

        # Calculate delta (new words not in previous translation)
        if previous_translation:
            prev_words = previous_translation.split()
            full_words = full_translation.split()

            # Find where new words start
            # Simple approach: assume translation grows monotonically
            delta_words = full_words[len(prev_words):]
            delta = " ".join(delta_words)
        else:
            delta = full_translation

        return TranslationResult(
            delta=delta,
            full_translation=full_translation,
            latency_ms=latency_ms,
        )


@dataclass
class StreamingTranslator:
    """
    Handles incremental translation with stable word detection.

    Orchestrates: interim detection -> LLM translation -> TTS queueing
    """

    translator: IncrementalTranslator
    source_lang: str = "Russian"
    target_lang: str = "English"
    stability_threshold: int = 2  # Number of interims for word to be "stable"
    min_words_for_tts: int = 2  # Minimum new words before sending to TTS

    # State
    interim_history: list[str] = field(default_factory=list)
    last_stable_source: str = ""
    translated_prefix: str = ""
    spoken_word_count: int = 0

    # Metrics
    speech_start_time: float | None = None
    first_audio_time: float | None = None
    llm_latencies: list[float] = field(default_factory=list)

    def reset(self) -> None:
        """Reset state for new utterance."""
        self.interim_history.clear()
        self.last_stable_source = ""
        self.translated_prefix = ""
        self.spoken_word_count = 0
        self.speech_start_time = None
        self.first_audio_time = None

    def get_stable_prefix(self, current_text: str) -> str:
        """
        Get words that haven't changed across recent interims.

        A word is "stable" if it appears at the same position
        in the last N interim results.
        """
        words = current_text.split()
        if len(self.interim_history) < self.stability_threshold:
            # Not enough history, but if we have context from previous
            # utterances, we can be more aggressive
            if self.translated_prefix:
                # We have previous context, use threshold of 1
                return current_text if len(self.interim_history) >= 1 else ""
            return ""

        # Find common prefix across recent interims
        recent = self.interim_history[-self.stability_threshold :]
        stable_count = 0

        for i, word in enumerate(words):
            is_stable = all(
                len(h.split()) > i and h.split()[i] == word for h in recent
            )
            if is_stable:
                stable_count = i + 1
            else:
                break

        return " ".join(words[:stable_count])

    async def process_interim(self, text: str) -> TranslationResult | None:
        """
        Process interim transcript.

        Returns TranslationResult if there are new words to speak,
        None otherwise.
        """
        text = text.strip()
        if not text:
            return None

        self.interim_history.append(text)

        # Get stable prefix
        stable = self.get_stable_prefix(text)
        if not stable:
            return None

        # Check if we have new stable words to translate
        if stable == self.last_stable_source:
            return None  # No new stable words

        # Translate the delta
        result = await self.translator.translate_delta(
            current_source=stable,
            previous_source=self.last_stable_source,
            previous_translation=self.translated_prefix,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
        )

        self.llm_latencies.append(result.latency_ms)

        # Check if we have enough new words
        delta_word_count = len(result.delta.split()) if result.delta else 0
        if delta_word_count < self.min_words_for_tts:
            # Not enough words yet, but update state for next iteration
            # Actually, don't update - wait for more words
            return None

        # Update state
        self.last_stable_source = stable
        self.translated_prefix = result.full_translation

        # Track first audio time
        if self.first_audio_time is None and self.speech_start_time:
            self.first_audio_time = time.time()

        return result

    def process_final(self, translated_text: str) -> str | None:
        """
        Process final transcript from Gladia (already translated).

        Returns remaining words to speak (not yet spoken), or None.
        """
        translated_text = translated_text.strip()
        if not translated_text:
            return None

        final_words = translated_text.split()

        # Get words we haven't spoken yet
        remaining_words = final_words[self.spoken_word_count :]

        if remaining_words:
            return " ".join(remaining_words)

        return None

    def get_metrics(self) -> dict:
        """Get current metrics."""
        return {
            "interim_count": len(self.interim_history),
            "spoken_words": self.spoken_word_count,
            "avg_llm_latency_ms": (
                sum(self.llm_latencies) / len(self.llm_latencies)
                if self.llm_latencies
                else 0
            ),
            "time_to_first_audio_ms": (
                (self.first_audio_time - self.speech_start_time) * 1000
                if self.first_audio_time and self.speech_start_time
                else None
            ),
        }
