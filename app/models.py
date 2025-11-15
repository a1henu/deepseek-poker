from __future__ import annotations

from dataclasses import dataclass, field
import secrets
from typing import List, Optional


def generate_secret() -> str:
    return secrets.token_hex(16)


@dataclass
class Player:
    id: str
    name: str
    stack: int
    is_ai: bool = False
    is_host: bool = False
    secret: str = field(default_factory=generate_secret)
    bet: int = 0
    folded: bool = False
    all_in: bool = False
    busted: bool = False
    hole_cards: list["Card"] = field(default_factory=list)
    has_acted: bool = False
    seat_index: int = 0

    def reset_for_new_hand(self) -> None:
        if self.stack <= 0:
            self.busted = True
        self.bet = 0
        self.folded = False
        self.all_in = False
        self.hole_cards = []
        self.has_acted = False

    @property
    def in_hand(self) -> bool:
        return not self.folded and not self.busted and self.stack >= 0

    def as_dict(self, reveal_cards: bool = False, include_secret: bool = False) -> dict:
        payload = {
            "id": self.id,
            "name": self.name,
            "stack": self.stack,
            "bet": self.bet,
            "is_ai": self.is_ai,
            "is_host": self.is_host,
            "folded": self.folded,
            "all_in": self.all_in,
            "busted": self.busted,
            "seat": self.seat_index,
        }
        if reveal_cards:
            payload["cards"] = [str(card) for card in self.hole_cards]
        else:
            payload["cards"] = len(self.hole_cards)
        if include_secret:
            payload["secret"] = self.secret
        return payload


@dataclass
class ActionRecord:
    player_id: str
    player_name: str
    action: str
    amount: int
    phase: str

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "action": self.action,
            "amount": self.amount,
            "phase": self.phase,
        }


# only for type checking
class Card:  # pragma: no cover - placeholder type
    pass
