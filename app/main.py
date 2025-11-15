from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import DeepSeekClient
from .config import load_settings
from .rooms import RoomManager
from .schemas import ActionRequest, CreateRoomRequest, JoinRoomRequest, StartHandRequest

settings = load_settings()
ai_client = DeepSeekClient(settings)
room_manager = RoomManager(settings=settings, ai_client=ai_client)

app = FastAPI(title="DeepSeek Poker Server", version="0.1.0")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await ai_client.close()


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def frontpage() -> FileResponse | dict:
    if WEB_DIR.exists():
        return FileResponse(WEB_DIR / "index.html")
    return {"message": "DeepSeek Poker API"}


@app.get("/rooms")
async def list_rooms() -> dict:
    rooms = await room_manager.list_rooms()
    return {"rooms": rooms}


@app.post("/rooms")
async def create_room(request: CreateRoomRequest) -> dict:
    stack = request.starting_stack or settings.starting_stack
    small_blind = request.small_blind or settings.small_blind
    big_blind = request.big_blind or settings.big_blind
    room, host = await room_manager.create_room(
        host_name=request.host_name,
        seats=request.total_seats,
        ai_players=request.ai_players,
        stack=stack,
        small_blind=small_blind,
        big_blind=big_blind,
    )
    async with room.lock:
        state = room.state_for(host)
    return {"room_id": room.id, "player_id": host.id, "player_secret": host.secret, "state": state}


@app.post("/rooms/{room_id}/join")
async def join_room(room_id: str, request: JoinRoomRequest) -> dict:
    player = await room_manager.join_room(room_id, request.player_name)
    room = room_manager.get_room(room_id)
    async with room.lock:
        state = room.state_for(player)
    return {"room_id": room_id, "player_id": player.id, "player_secret": player.secret, "state": state}


@app.post("/rooms/{room_id}/start")
async def start_hand(room_id: str, request: StartHandRequest) -> dict:
    state = await room_manager.start_hand(room_id, request.player_id, request.player_secret)
    return {"room_id": room_id, "state": state}


@app.post("/rooms/{room_id}/action")
async def player_action(room_id: str, request: ActionRequest) -> dict:
    amount = request.amount or 0
    state = await room_manager.submit_action(
        room_id,
        request.player_id,
        request.player_secret,
        request.action,
        amount,
    )
    return {"room_id": room_id, "state": state}


@app.get("/rooms/{room_id}")
async def room_state(room_id: str, player_id: str | None = None, player_secret: str | None = None) -> dict:
    state = await room_manager.fetch_state(room_id, player_id, player_secret)
    return {"room_id": room_id, "state": state}
