from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

import httpx

from .config import Settings


@dataclass
class ActionDecision:
    action: str
    amount: int = 0
    explanation: str | None = None


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model
        self.url = settings.deepseek_url
        self.http = httpx.AsyncClient(timeout=20)

    async def close(self) -> None:
        await self.http.aclose()

    async def choose_action(self, context: Dict[str, Any]) -> ActionDecision:
        if not self.api_key:
            return self._fallback(context, "Missing DEEPSEEK_API_KEY")
        messages = self._build_messages(context)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": messages, "temperature": 0.2}
        try:
            response = await self.http.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return self._fallback(context, f"DeepSeek request failed: {exc}")
        try:
            content = response.json()
            message = content["choices"][0]["message"]["content"]
            decision = self._parse_decision(message)
        except Exception as exc:  # noqa: BLE001
            return self._fallback(context, f"Malformed DeepSeek response: {exc}")
        if decision.action not in context.get("legal_actions", []):
            return self._fallback(context, "Illegal action suggested")
        return decision

    def _build_messages(self, context: Dict[str, Any]) -> list[dict]:
        history = context.get("actions", [])
        history_lines = [
            f"- {item['player_name']} -> {item['action']} ({item['amount']}) during {item['phase']}"
            for item in history[-12:]
        ]
        history_text = "\n".join(history_lines) or "No actions yet."
        board = ", ".join(context.get("community_cards", [])) or "None"
        cards = ", ".join(context.get("hole_cards", [])) or "Unknown"
        legal = ", ".join(context.get("legal_actions", []))
        prompt = (
            "You control a single seat in a No-Limit Texas Hold'em poker game. "
            "Always return a single JSON object with fields action, amount, and explanation. "
            "Allowed actions: fold, check, call, bet, raise. "
            "For bet/raise set amount to the FINAL total bet size (chips in front of you after the action). "
            f"\nCommunity cards: {board}"
            f"\nYour hole cards: {cards}"
            f"\nCurrent pot: {context.get('pot')} | Stack: {context.get('stack')} | To call: {context.get('to_call')} | Min raise: {context.get('min_raise')}"
            f"\nCurrent phase: {context.get('phase')}"
            f"\nAction history:\n{history_text}"
            f"\nLegal actions right now: {legal}"
            "\nOnly output JSON like {\"action\":\"call\",\"amount\":0,\"explanation\":\"reason\"}."
        )
        return [
            {
                "role": "system",
                "content": "You are DeepSeek, a disciplined poker assistant. Always obey the betting rules.",
            },
            {"role": "user", "content": prompt},
        ]

    def _parse_decision(self, message: str) -> ActionDecision:
        start = message.find("{")
        end = message.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object in response")
        data = json.loads(message[start : end + 1])
        action = data.get("action", "").lower()
        amount = int(data.get("amount", 0))
        explanation = data.get("explanation")
        return ActionDecision(action=action, amount=amount, explanation=explanation)

    def _fallback(self, context: Dict[str, Any], reason: str) -> ActionDecision:
        legal = context.get("legal_actions", [])
        to_call = context.get("to_call", 0)
        stack = context.get("stack", 0)
        if "check" in legal:
            return ActionDecision(action="check", amount=0, explanation=reason)
        if "call" in legal and stack >= to_call:
            return ActionDecision(action="call", amount=to_call, explanation=reason)
        return ActionDecision(action="fold", explanation=reason)

