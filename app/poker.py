from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .models import ActionRecord, Player


RANKS = "23456789TJQKA"
SUITS = "SHDC"
RANK_VALUES = {rank: index + 2 for index, rank in enumerate(RANKS)}
HAND_NAMES = [
    "High Card",
    "Pair",
    "Two Pair",
    "Three of a Kind",
    "Straight",
    "Flush",
    "Full House",
    "Four of a Kind",
    "Straight Flush",
]


@dataclass(slots=True)
class Card:
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def to_dict(self) -> dict:
        return {"rank": self.rank, "suit": self.suit, "label": str(self)}


def fresh_deck() -> list[Card]:
    return [Card(rank, suit) for rank in RANKS for suit in SUITS]


@dataclass(slots=True)
class HandStrength:
    rank_value: int
    name: str
    kickers: List[int]
    best_cards: List[Card]


def evaluate_best_hand(hole_cards: Sequence[Card], board: Sequence[Card]) -> HandStrength:
    cards = list(hole_cards) + list(board)
    best: HandStrength | None = None
    for combo in itertools.combinations(cards, 5):
        strength = evaluate_five_card_hand(combo)
        if best is None or compare_strength(strength, best) > 0:
            best = strength
    if best is None:
        raise ValueError("unable to evaluate hand")
    return best


def evaluate_five_card_hand(cards: Sequence[Card]) -> HandStrength:
    values = sorted((RANK_VALUES[c.rank] for c in cards), reverse=True)
    suits = [c.suit for c in cards]
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    is_flush = len(set(suits)) == 1
    straight_high = detect_straight(values)
    if is_flush and straight_high:
        return HandStrength(8, HAND_NAMES[8], [straight_high], list(cards))
    max_count = ordered[0][1]
    if max_count == 4:
        quad = ordered[0][0]
        kicker = max(v for v in values if v != quad)
        return HandStrength(7, HAND_NAMES[7], [quad, kicker], list(cards))
    if max_count == 3 and len(ordered) > 1 and ordered[1][1] >= 2:
        trips = ordered[0][0]
        pair = ordered[1][0]
        return HandStrength(6, HAND_NAMES[6], [trips, pair], list(cards))
    if is_flush:
        return HandStrength(5, HAND_NAMES[5], values, list(cards))
    if straight_high:
        return HandStrength(4, HAND_NAMES[4], [straight_high], list(cards))
    if max_count == 3:
        trips = ordered[0][0]
        kickers = [v for v in values if v != trips][:2]
        return HandStrength(3, HAND_NAMES[3], [trips, *kickers], list(cards))
    if max_count == 2 and len(ordered) > 1 and ordered[1][1] == 2:
        pair_high = max(ordered[0][0], ordered[1][0])
        pair_low = min(ordered[0][0], ordered[1][0])
        kicker = max(v for v in values if v not in (pair_high, pair_low))
        return HandStrength(2, HAND_NAMES[2], [pair_high, pair_low, kicker], list(cards))
    if max_count == 2:
        pair = ordered[0][0]
        kickers = [v for v in values if v != pair][:3]
        return HandStrength(1, HAND_NAMES[1], [pair, *kickers], list(cards))
    return HandStrength(0, HAND_NAMES[0], values, list(cards))


def detect_straight(values: Iterable[int]) -> int | None:
    unique = sorted(set(values))
    if {14, 5, 4, 3, 2}.issubset(unique):
        return 5
    for i in range(len(unique) - 4):
        window = unique[i : i + 5]
        if window == list(range(window[0], window[0] + 5)):
            return window[-1]
    return None


def compare_strength(left: HandStrength, right: HandStrength) -> int:
    if left.rank_value != right.rank_value:
        return left.rank_value - right.rank_value
    for l, r in itertools.zip_longest(left.kickers, right.kickers, fillvalue=0):
        if l != r:
            return l - r
    return 0


class PokerHand:
    def __init__(
        self,
        players: list[Player],
        dealer_index: int,
        small_blind: int,
        big_blind: int,
    ) -> None:
        self.players = players
        self.dealer_index = dealer_index
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.deck: list[Card] = []
        self.community_cards: list[Card] = []
        self.pot: int = 0
        self.phase: str = "waiting"
        self.current_bet: int = 0
        self.min_raise: int = big_blind
        self.current_player_index: int | None = None
        self.actions: list[ActionRecord] = []
        self.hand_over = False
        self.winners: list[dict] = []
        self.last_event: str | None = None
        self.small_blind_index: int | None = None
        self.big_blind_index: int | None = None

    def start(self) -> None:
        active_players = [p for p in self.players if p.stack > 0 and not p.busted]
        if len(active_players) < 2:
            raise ValueError("not enough players with chips")
        self.deck = fresh_deck()
        random.shuffle(self.deck)
        for seat, player in enumerate(self.players):
            player.seat_index = seat
            player.reset_for_new_hand()
        self.community_cards = []
        self.pot = 0
        self.phase = "preflop"
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.actions = []
        self.winners = []
        self.hand_over = False
        self.last_event = None
        self._deal_private_cards()
        sb_index = self._next_active_index(self.dealer_index)
        bb_index = self._next_active_index(sb_index)
        if sb_index is None or bb_index is None:
            raise ValueError("unable to post blinds")
        self.small_blind_index = sb_index
        self.big_blind_index = bb_index
        self._post_blind(sb_index, self.small_blind, "small_blind")
        self._post_blind(bb_index, self.big_blind, "big_blind")
        self.current_bet = max(player.bet for player in self.players)
        self.min_raise = self.big_blind
        self.current_player_index = self._next_active_index(bb_index)
        if self.current_player_index is None:
            self._resolve_showdown()

    def _deal_private_cards(self) -> None:
        for _ in range(2):
            for idx in self._iter_from(self.dealer_index):
                player = self.players[idx]
                if player.stack <= 0 or player.busted:
                    continue
                player.hole_cards.append(self.deck.pop())

    def _iter_from(self, start: int):
        total = len(self.players)
        idx = (start + 1) % total
        for _ in range(total):
            yield idx
            idx = (idx + 1) % total

    def _next_active_index(self, start_index: int | None) -> int | None:
        if start_index is None:
            return None
        for idx in self._iter_from(start_index):
            player = self.players[idx]
            if player.folded or player.busted or player.stack <= 0 and not player.all_in:
                continue
            if player.all_in:
                continue
            return idx
        return None

    def _post_blind(self, player_index: int, amount: int, label: str) -> None:
        player = self.players[player_index]
        chips = min(player.stack, amount)
        self._commit(player, chips)
        record = ActionRecord(
            player_id=player.id,
            player_name=player.name,
            action=label,
            amount=chips,
            phase=self.phase,
        )
        self.actions.append(record)

    def _commit(self, player: Player, amount: int) -> None:
        amount = max(0, min(amount, player.stack))
        player.stack -= amount
        player.bet += amount
        self.pot += amount
        if player.stack == 0 and amount > 0:
            player.all_in = True

    @property
    def current_player(self) -> Player | None:
        if self.current_player_index is None:
            return None
        return self.players[self.current_player_index]

    def legal_actions(self, player: Player) -> list[str]:
        if self.hand_over or player.folded or player.all_in or player.busted:
            return []
        to_call = max(0, self.current_bet - player.bet)
        options: list[str] = []
        if to_call > 0:
            options.append("fold")
            options.append("call")
            if player.stack + player.bet > self.current_bet:
                options.append("raise")
        else:
            options.append("check")
            if player.stack > 0:
                options.append("bet")
        return options

    def apply_action(self, player: Player, action: str, amount: int = 0) -> None:
        if self.hand_over:
            raise ValueError("hand already finished")
        if player is not self.current_player:
            raise ValueError("not this player's turn")
        to_call = max(0, self.current_bet - player.bet)
        action = action.lower()
        if action not in {"fold", "check", "call", "bet", "raise"}:
            raise ValueError("unknown action")
        logged_amount = 0
        if action == "fold":
            player.folded = True
        elif action == "check":
            if to_call != 0:
                raise ValueError("cannot check facing a bet")
        elif action == "call":
            if to_call == 0:
                raise ValueError("nothing to call")
            logged_amount = min(player.stack, to_call)
            self._commit(player, to_call)
        elif action == "bet":
            if self.current_bet != 0:
                raise ValueError("bet not allowed, must raise")
            if amount <= 0:
                raise ValueError("bet amount must be positive")
            if amount < self.big_blind:
                raise ValueError("bet must be at least the big blind")
            desired_total = min(player.bet + player.stack, amount)
            commit = desired_total - player.bet
            if commit <= 0:
                raise ValueError("insufficient chips to bet")
            self._commit(player, commit)
            self.current_bet = player.bet
            self.min_raise = commit
            logged_amount = player.bet
        elif action == "raise":
            if self.current_bet == 0:
                raise ValueError("nothing to raise")
            if amount <= self.current_bet:
                raise ValueError("raise must increase bet")
            min_total = self.current_bet + self.min_raise
            desired_total = max(amount, min_total)
            desired_total = min(player.bet + player.stack, desired_total)
            commit = desired_total - player.bet
            if commit <= to_call:
                raise ValueError("raise must exceed call amount")
            self._commit(player, commit)
            self.min_raise = desired_total - self.current_bet
            self.current_bet = desired_total
            logged_amount = player.bet
        player.has_acted = True
        record = ActionRecord(
            player_id=player.id,
            player_name=player.name,
            action=action,
            amount=logged_amount,
            phase=self.phase,
        )
        self.actions.append(record)
        if self._active_player_count() <= 1:
            self._finish_single_player()
            return
        self._advance_turn_or_round()

    def _advance_turn_or_round(self) -> None:
        next_index = self._find_next_to_act()
        if next_index is None:
            self._complete_betting_round()
        else:
            self.current_player_index = next_index

    def _find_next_to_act(self) -> int | None:
        if self.current_player_index is None:
            return None
        for idx in self._iter_from(self.current_player_index):
            player = self.players[idx]
            if player.folded or player.busted or player.all_in:
                continue
            if player.bet != self.current_bet:
                return idx
            if not player.has_acted:
                return idx
        return None

    def _complete_betting_round(self) -> None:
        for player in self.players:
            player.bet = 0
            player.has_acted = False
        self.current_bet = 0
        self.min_raise = self.big_blind
        if self.phase == "river":
            self._resolve_showdown()
            return
        self._advance_board()
        self.current_player_index = self._next_active_index(self.dealer_index)
        if self.current_player_index is None:
            self._resolve_showdown()

    def _advance_board(self) -> None:
        if self.phase == "preflop":
            self.phase = "flop"
            for _ in range(3):
                self.community_cards.append(self.deck.pop())
        elif self.phase == "flop":
            self.phase = "turn"
            self.community_cards.append(self.deck.pop())
        elif self.phase == "turn":
            self.phase = "river"
            self.community_cards.append(self.deck.pop())

    def _deal_remaining_board(self) -> None:
        while len(self.community_cards) < 5 and self.deck:
            self.community_cards.append(self.deck.pop())

    def _resolve_showdown(self) -> None:
        self._deal_remaining_board()
        contenders = [p for p in self.players if not p.folded and not p.busted]
        if not contenders:
            self._finish_hand([], "no players left")
            return
        scored = [(evaluate_best_hand(p.hole_cards, self.community_cards), p) for p in contenders]
        scored.sort(key=lambda item: (item[0].rank_value, item[0].kickers), reverse=True)
        best_rank = scored[0][0]
        winners = [p for strength, p in scored if compare_strength(strength, best_rank) == 0]
        self._award_pot(winners, best_rank)

    def _finish_single_player(self) -> None:
        remaining = [p for p in self.players if not p.folded and not p.busted]
        if not remaining:
            self._finish_hand([], "hand aborted")
            return
        self._award_pot([remaining[0]], None)

    def _award_pot(self, winners: list[Player], strength: HandStrength | None) -> None:
        if not winners:
            self.hand_over = True
            self.pot = 0
            self.current_player_index = None
            self.phase = "showdown"
            return
        share, remainder = divmod(self.pot, len(winners))
        for idx, player in enumerate(winners):
            player.stack += share + (1 if idx < remainder else 0)
        self.last_event = f"{', '.join(p.name for p in winners)} won {self.pot} chips"
        self.winners = [
            {
                "player_id": p.id,
                "player_name": p.name,
                "hand": strength.name if strength else "No contest",
                "cards": [str(card) for card in p.hole_cards],
            }
            for p in winners
        ]
        self.pot = 0
        self.hand_over = True
        self.current_player_index = None
        self.phase = "showdown"

    def _finish_hand(self, winners: list[Player], message: str) -> None:
        self.winners = [{"player_id": p.id, "player_name": p.name, "hand": message, "cards": []} for p in winners]
        self.last_event = message
        self.pot = 0
        self.current_player_index = None
        self.hand_over = True
        self.phase = "showdown"

    def _active_player_count(self) -> int:
        return len([p for p in self.players if not p.folded and not p.busted])

    def everyone_all_in(self) -> bool:
        alive = [p for p in self.players if not p.folded and not p.busted]
        return all(p.all_in for p in alive)

    def build_ai_context(self, player: Player) -> dict:
        to_call = max(0, self.current_bet - player.bet)
        legal = self.legal_actions(player)
        return {
            "player_id": player.id,
            "player_name": player.name,
            "hole_cards": [str(card) for card in player.hole_cards],
            "community_cards": [str(card) for card in self.community_cards],
            "pot": self.pot,
            "stack": player.stack,
            "to_call": to_call,
            "min_raise": self.min_raise,
            "phase": self.phase,
            "legal_actions": legal,
            "actions": [record.to_dict() for record in self.actions],
        }

    def fallback_action(self, player: Player) -> tuple[str, int]:
        to_call = max(0, self.current_bet - player.bet)
        legal = self.legal_actions(player)
        if "check" in legal:
            return "check", 0
        if "call" in legal and player.stack >= to_call:
            return "call", to_call
        return "fold", 0
