"""
Token Server for PWA

Simple HTTP server that:
1. Serves static files from ./static
2. Provides /api/token endpoint for LiveKit tokens
3. Creates room with metadata for agent to read direction

Usage:
    uv run python server.py
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from aiohttp import web
from livekit import api

load_dotenv(".env.local")

LIVEKIT_URL = os.environ["LIVEKIT_URL"]
STATIC_DIR = Path(__file__).parent / "static"

lkapi: api.LiveKitAPI | None = None


async def get_token(request: web.Request) -> web.Response:
    """Generate LiveKit token and create room with direction metadata."""
    global lkapi
    if lkapi is None:
        lkapi = api.LiveKitAPI(LIVEKIT_URL)

    direction = request.query.get("direction", "ru-en")
    room_name = f"translate-{uuid.uuid4().hex[:8]}"

    # Create room with direction as metadata
    await lkapi.room.create_room(
        api.CreateRoomRequest(name=room_name, metadata=direction)
    )

    token = (
        api.AccessToken()
        .with_identity(f"user-{uuid.uuid4().hex[:6]}")
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        ))
        .to_jwt()
    )

    return web.json_response({
        "token": token,
        "url": LIVEKIT_URL,
        "room": room_name,
        "direction": direction,
    })


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/token", get_token)
    app.router.add_static("/static", STATIC_DIR)
    return app


if __name__ == "__main__":
    STATIC_DIR.mkdir(exist_ok=True)
    print(f"Server: http://localhost:8080")
    print(f"Static: {STATIC_DIR}")
    web.run_app(create_app(), port=8080)
