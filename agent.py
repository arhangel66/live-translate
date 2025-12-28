"""
Live Voice Translator Agent

Microphone -> Gladia STT (with translation) -> Cartesia TTS -> Headphones

Streaming mode: Uses LLM for interim translation to reduce latency.

Usage:
    uv run python agent.py dev
"""

import asyncio
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.agents import UserInputTranscribedEvent, UserStateChangedEvent
from livekit.agents.voice.speech_handle import SpeechHandle
from livekit.plugins import cartesia, gladia

from translator import IncrementalTranslator, StreamingTranslator

load_dotenv(".env.local")


@dataclass
class TranslationMetrics:
    """Tracks translation pipeline metrics."""

    stt_times: list[float] = field(default_factory=list)
    tts_times: list[float] = field(default_factory=list)
    total_times: list[float] = field(default_factory=list)

    def add(self, stt_ms: float, tts_ms: float, total_ms: float) -> None:
        self.stt_times.append(stt_ms)
        self.tts_times.append(tts_ms)
        self.total_times.append(total_ms)

    def avg(self, times: list[float]) -> float:
        return sum(times) / len(times) if times else 0

    def summary(self) -> str:
        n = len(self.total_times)
        if n == 0:
            return "No data yet"
        return (
            f"[{n} samples] "
            f"STT: {self.avg(self.stt_times):.0f}ms | "
            f"TTS: {self.avg(self.tts_times):.0f}ms | "
            f"Total: {self.avg(self.total_times):.0f}ms"
        )

CARTESIA_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"

LANG_CONFIG = {
    "ru-en": {"source": "ru", "target": "en", "source_name": "Russian", "target_name": "English"},
    "en-ru": {"source": "en", "target": "ru", "source_name": "English", "target_name": "Russian"},
}


class TranslatorAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a live translator.")


def create_session(direction: str) -> AgentSession:
    """Create agent session for given translation direction."""
    config = LANG_CONFIG.get(direction, LANG_CONFIG["ru-en"])
    source, target = config["source"], config["target"]

    stt = gladia.STT(
        languages=[source, target],
        interim_results=True,
        translation_enabled=True,
        translation_target_languages=[target],
    )

    tts = cartesia.TTS(
        model="sonic-turbo",
        voice=CARTESIA_VOICE_ID,
        language=target,
    )

    return AgentSession(stt=stt, tts=tts, allow_interruptions=False)


server = agents.AgentServer()


@server.rtc_session()
async def translator_session(ctx: agents.JobContext) -> None:
    """Main translator session with streaming translation."""
    # Get direction from room metadata or default
    direction = ctx.room.metadata or "ru-en"
    config = LANG_CONFIG.get(direction, LANG_CONFIG["ru-en"])
    print(f"[translator] direction={direction}")

    session = create_session(direction)
    metrics = TranslationMetrics()

    # Create streaming translator
    llm_translator = IncrementalTranslator()
    streaming = StreamingTranslator(
        translator=llm_translator,
        source_lang=config["source_name"],
        target_lang=config["target_name"],
        stability_threshold=2,
        min_words_for_tts=2,
    )

    @session.on("user_state_changed")
    def on_user_state(event: UserStateChangedEvent) -> None:
        if event.new_state == "speaking":
            streaming.speech_start_time = time.time()
        elif event.old_state == "speaking" and event.new_state == "listening":
            # User stopped speaking, reset for next utterance after final
            pass

    @session.on("user_input_transcribed")
    def on_transcribed(event: UserInputTranscribedEvent) -> None:
        text = event.transcript.strip()
        if not text:
            return

        if event.is_final:
            # Final transcript from Gladia (contains translation)
            print(f"[final] {text}")

            # Get remaining words not yet spoken
            remaining = streaming.process_final(text)
            if remaining:
                print(f"[tts:final] {remaining}")
                tts_start = time.time()
                handle = session.say(remaining, allow_interruptions=False)

                def on_final_done(_: SpeechHandle) -> None:
                    tts_end = time.time()
                    tts_ms = (tts_end - tts_start) * 1000
                    total_ms = (
                        (tts_end - streaming.speech_start_time) * 1000
                        if streaming.speech_start_time
                        else 0
                    )

                    # Get streaming metrics
                    stream_metrics = streaming.get_metrics()
                    stt_ms = stream_metrics.get("time_to_first_audio_ms") or total_ms

                    metrics.add(stt_ms, tts_ms, total_ms)
                    print(
                        f"[metrics] FirstAudio: {stt_ms:.0f}ms | "
                        f"LLM: {stream_metrics['avg_llm_latency_ms']:.0f}ms | "
                        f"Total: {total_ms:.0f}ms"
                    )

                    # Send metrics to UI
                    asyncio.create_task(
                        send_metrics_to_ui(
                            ctx.room,
                            stt_ms,
                            tts_ms,
                            total_ms,
                            llm_ms=stream_metrics["avg_llm_latency_ms"],
                        )
                    )

                handle.add_done_callback(on_final_done)

            # Reset for next utterance
            streaming.reset()

        else:
            # Interim transcript (original language) - translate incrementally
            print(f"[interim] {text}")

            async def process_and_speak() -> None:
                result = await streaming.process_interim(text)
                if result and result.delta:
                    print(f"[tts:interim] {result.delta} (LLM: {result.latency_ms:.0f}ms)")
                    handle = session.say(result.delta, allow_interruptions=True)
                    streaming.spoken_word_count += len(result.delta.split())

            asyncio.create_task(process_and_speak())

    await session.start(
        room=ctx.room,
        agent=TranslatorAgent(),
        room_input_options=RoomInputOptions(text_enabled=False),
    )

    await asyncio.Future()


async def send_metrics_to_ui(
    room: rtc.Room,
    stt_ms: float,
    tts_ms: float,
    total_ms: float,
    llm_ms: float = 0,
) -> None:
    """Send metrics to UI via data channel."""
    import json

    data = json.dumps({
        "type": "metrics",
        "stt_ms": round(stt_ms),
        "tts_ms": round(tts_ms),
        "total_ms": round(total_ms),
        "llm_ms": round(llm_ms),
    })

    try:
        await room.local_participant.publish_data(data.encode(), reliable=True)
    except Exception as e:
        print(f"[metrics] Failed to send: {e}")


if __name__ == "__main__":
    agents.cli.run_app(server)
