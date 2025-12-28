"""
Live Voice Translator Agent

Microphone -> Gladia STT (with translation) -> Cartesia TTS -> Headphones

Usage:
    uv run python agent.py dev
"""

import asyncio

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.agents import UserInputTranscribedEvent
from livekit.plugins import cartesia, gladia

load_dotenv(".env.local")

CARTESIA_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"

LANG_CONFIG = {
    "ru-en": {"source": "ru", "target": "en"},
    "en-ru": {"source": "en", "target": "ru"},
}

# Technical terms that should be preserved or translated correctly
CUSTOM_VOCABULARY = [
    "LiveKit",
    "WebRTC",
    "API",
    "SDK",
    "Python",
    "JavaScript",
]


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
        # Quality improvements
        pre_processing_audio_enhancer=True,
        custom_vocabulary=CUSTOM_VOCABULARY,
        translation_context_adaptation=True,
        # Speed improvements
        endpointing=0.05,
        maximum_duration_without_endpointing=3,
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
    """Main translator session."""
    # Get direction from room metadata or default
    direction = ctx.room.metadata or "ru-en"
    print(f"[translator] direction={direction}")

    session = create_session(direction)

    @session.on("user_input_transcribed")
    def on_transcribed(event: UserInputTranscribedEvent) -> None:
        if event.is_final:
            text = event.transcript.strip()
            if text:
                print(f"[{event.language}] {text}")
                session.say(text, allow_interruptions=False)

    await session.start(
        room=ctx.room,
        agent=TranslatorAgent(),
        room_input_options=RoomInputOptions(text_enabled=False),
    )

    await asyncio.Future()


if __name__ == "__main__":
    agents.cli.run_app(server)
