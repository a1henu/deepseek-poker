from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import HTTPException

from .ai import DeepSeekClient
from .config import Settings
from .models import Player
from .poker import PokerHand


def create_player(name: str, stack: int, is_ai: bool = False, is_host: bool = False) -> Player:
    return Player(id=str(uuid.uuid4()), name=name, stack=stack, is_ai=is_ai, is_host=is_host)


class Room:
    def __init__(
        self,
        room_id: str,
        host: Player,
        seats: int,
        ai_players: int,
        stack: int,
        small_blind: int,
        big_blind: int,
        ai_client: DeepSeekClient,
    ) -> None:
        self.id = room_id
        self.players: list[Player] = [host]
        self.total_seats = seats
        self.ai_requested = ai_players
        self.starting_stack = stack
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.ai_client = ai_client
        self.created_at = datetime.utcnow()
        self.lock = asyncio.Lock()
        self.host_player_id = host.id
        self.game: PokerHand | None = None
        self.dealer_index: int | None = None
        self.state_version: int = 1

    def _human_slots(self) -> int:
        return self.total_seats - self.ai_requested

    def _human_count(self) -> int:
        return len([p for p in self.players if not p.is_ai])

    def ensure_space_for_human(self) -> None:
        if self._human_count() >= self._human_slots():
            raise HTTPException(status_code=400, detail="Room is full for human players")

    def add_player(self, name: str, is_ai: bool = False) -> Player:
        if not is_ai:
            self.ensure_space_for_human()
        if len(self.players) >= self.total_seats:
            raise HTTPException(status_code=400, detail="Room is at capacity")
        player = create_player(name=name, stack=self.starting_stack, is_ai=is_ai)
        player.seat_index = len(self.players)
        self.players.append(player)
        self.state_version += 1
        return player

    def get_player(self, player_id: str) -> Player:
        for player in self.players:
            if player.id == player_id:
                return player
        raise HTTPException(status_code=404, detail="Player not found")

    def verify_secret(self, player_id: str, secret: str) -> Player:
        player = self.get_player(player_id)
        if player.secret != secret:
            raise HTTPException(status_code=403, detail="Invalid player secret")
        return player

    def _spawn_ai_players(self) -> None:
        current_ai = len([p for p in self.players if p.is_ai])
        needed = self.ai_requested - current_ai
        for index in range(needed):
            bot = self.add_player(name=f"Bot {current_ai + index + 1}", is_ai=True)
            bot.secret = ""

    def _active_indices(self) -> list[int]:
        return [idx for idx, player in enumerate(self.players) if player.stack > 0 and not player.busted]

    def _next_dealer_position(self) -> int:
        alive = self._active_indices()
        if not alive:
            raise HTTPException(status_code=400, detail="No players with chips")
        if self.dealer_index is None:
            return random.choice(alive)
        iterator = list(range(len(self.players)))
        start = (self.dealer_index + 1) % len(self.players)
        for offset in range(len(self.players)):
            idx = (start + offset) % len(self.players)
            if idx in alive:
                return idx
        return alive[0]

    def start_hand(self, requesting_player: Player) -> None:
        if requesting_player.id != self.host_player_id:
            raise HTTPException(status_code=403, detail="Only the host can start a hand")
        if self.game and not self.game.hand_over:
            raise HTTPException(status_code=400, detail="当前牌局尚未结束，不能重新开局")
        self._spawn_ai_players()
        if len([p for p in self.players if p.stack > 0]) < 2:
            raise HTTPException(status_code=400, detail="Need at least two players with chips")
        dealer = self._next_dealer_position()
        self.dealer_index = dealer
        self.game = PokerHand(
            players=self.players,
            dealer_index=dealer,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
        )
        self.game.start()
        self.state_version += 1

    async def handle_action(self, player: Player, action: str, amount: int) -> None:
        if not self.game:
            raise HTTPException(status_code=400, detail="No active hand")
        try:
            self.game.apply_action(player, action, amount)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        self.state_version += 1

    def _current_player(self) -> Player | None:
        if not self.game:
            return None
        return self.game.current_player

    async def auto_play_ai(self) -> None:
        while True:
            async with self.lock:
                current = self._current_player()
                if not current or not current.is_ai or not self.game or self.game.hand_over:
                    return
                context = self.game.build_ai_context(current)
            decision = await self.ai_client.choose_action(context)
            async with self.lock:
                if not self.game or self.game.hand_over:
                    return
                current = self._current_player()
                if not current or not current.is_ai:
                    continue
                try:
                    self.game.apply_action(current, decision.action, decision.amount)
                except ValueError:
                    fallback_action, fallback_amount = self.game.fallback_action(current)
                    self.game.apply_action(current, fallback_action, fallback_amount)
                self.state_version += 1
            await asyncio.sleep(0)

    def state_for(self, viewer: Player | None) -> dict:
        game = self.game
        state = {
            "room_id": self.id,
            "total_seats": self.total_seats,
            "ai_players": self.ai_requested,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "state_version": self.state_version,
            "created_at": self.created_at.isoformat() + "Z",
            "host_player_id": self.host_player_id,
            "players": [],
            "phase": "waiting",
            "pot": 0,
            "community_cards": [],
            "actions": [],
            "winners": [],
            "current_player_id": None,
            "last_event": None,
            "dealer_player_id": None,
            "small_blind_player_id": None,
            "big_blind_player_id": None,
            "current_bet": 0,
        }
        reveal_all = bool(game and game.hand_over)
        for player in self.players:
            reveal = reveal_all or (viewer and player.id == viewer.id)
            entry = player.as_dict(
                reveal_cards=reveal,
                include_secret=bool(viewer and viewer.id == player.id),
            )
            state["players"].append(entry)
        if game:
            state.update(
                {
                    "phase": game.phase,
                    "pot": game.pot,
                    "community_cards": [str(card) for card in game.community_cards],
                    "actions": [record.to_dict() for record in game.actions],
                    "winners": game.winners,
                    "current_player_id": game.current_player.id if game.current_player else None,
                    "last_event": game.last_event,
                    "current_bet": game.current_bet,
                    "dealer_player_id": (
                        game.players[game.dealer_index].id if game.dealer_index is not None else None
                    ),
                    "small_blind_player_id": (
                        game.players[game.small_blind_index].id
                        if game.small_blind_index is not None
                        else None
                    ),
                    "big_blind_player_id": (
                        game.players[game.big_blind_index].id
                        if game.big_blind_index is not None
                        else None
                    ),
                }
            )
        if viewer and game:
            to_call = max(0, game.current_bet - viewer.bet)
            state["self"] = {
                "player_id": viewer.id,
                "legal_actions": game.legal_actions(viewer),
                "to_call": to_call,
                "stack": viewer.stack,
            }
        return state


class RoomManager:
    def __init__(self, settings: Settings, ai_client: DeepSeekClient) -> None:
        self.settings = settings
        self.ai_client = ai_client
        self.rooms: Dict[str, Room] = {}
        self.lock = asyncio.Lock()

    def _new_room_id(self) -> str:
        return uuid.uuid4().hex[:6].upper()

    async def create_room(
        self,
        host_name: str,
        seats: int,
        ai_players: int,
        stack: int,
        small_blind: int,
        big_blind: int,
    ) -> tuple[Room, Player]:
        if seats < 2 or seats > 9:
            raise HTTPException(status_code=400, detail="Seats must be between 2 and 9")
        if ai_players >= seats:
            raise HTTPException(status_code=400, detail="AI players must be fewer than seats")
        host = create_player(host_name, stack, is_host=True)
        async with self.lock:
            if len(self.rooms) >= self.settings.max_rooms:
                raise HTTPException(status_code=503, detail="Room limit reached")
            room_id = self._new_room_id()
            room = Room(
                room_id=room_id,
                host=host,
                seats=seats,
                ai_players=ai_players,
                stack=stack,
                small_blind=small_blind,
                big_blind=big_blind,
                ai_client=self.ai_client,
            )
            self.rooms[room_id] = room
        return room, host

    def get_room(self, room_id: str) -> Room:
        room = self.rooms.get(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        return room

    async def join_room(self, room_id: str, name: str) -> Player:
        room = self.get_room(room_id)
        async with room.lock:
            return room.add_player(name)

    async def start_hand(self, room_id: str, player_id: str, secret: str) -> dict:
        room = self.get_room(room_id)
        async with room.lock:
            player = room.verify_secret(player_id, secret)
            room.start_hand(player)
        await room.auto_play_ai()
        async with room.lock:
            return room.state_for(player)

    async def submit_action(
        self, room_id: str, player_id: str, secret: str, action: str, amount: int
    ) -> dict:
        room = self.get_room(room_id)
        async with room.lock:
            player = room.verify_secret(player_id, secret)
            await room.handle_action(player, action, amount)
        await room.auto_play_ai()
        async with room.lock:
            return room.state_for(player)

    async def fetch_state(self, room_id: str, player_id: str | None, secret: str | None) -> dict:
        room = self.get_room(room_id)
        async with room.lock:
            viewer: Optional[Player] = None
            if player_id and secret:
                viewer = room.verify_secret(player_id, secret)
            return room.state_for(viewer)

    async def list_rooms(self) -> list[dict]:
        async with self.lock:
            rooms = list(self.rooms.values())
        summary = []
        for room in rooms:
            async with room.lock:
                summary.append(
                    {
                        "room_id": room.id,
                        "total_seats": room.total_seats,
                        "ai_players": room.ai_requested,
                        "humans": len([p for p in room.players if not p.is_ai]),
                        "phase": room.game.phase if room.game else "waiting",
                        "created_at": room.created_at.isoformat() + "Z",
                    }
                )
        return summary
