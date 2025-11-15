from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateRoomRequest(BaseModel):
    host_name: str = Field(..., min_length=1, max_length=32)
    total_seats: int = Field(..., ge=2, le=9)
    ai_players: int = Field(..., ge=0)
    starting_stack: Optional[int] = Field(None, ge=100)
    small_blind: Optional[int] = Field(None, ge=1)
    big_blind: Optional[int] = Field(None, ge=2)


class JoinRoomRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=32)


class StartHandRequest(BaseModel):
    player_id: str
    player_secret: str


class ActionRequest(BaseModel):
    player_id: str
    player_secret: str
    action: Literal["fold", "check", "call", "bet", "raise"]
    amount: int | None = Field(default=0, ge=0)

