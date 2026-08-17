from __future__ import annotations

from typing import Optional

from .config import (DEFAULT_TOTAL_SLOTS, DEFAULT_LIVE_BULLETS, DEFAULT_MODE,
                     DEFAULT_MAX_CHARGES, DEFAULT_ITEM_SET, get_player_templates)
from .game import GameSession
from .models import AIPlayer
from .tournament import RoundRobinRunner


def create_player(name: str, is_human: bool = False,
                  max_charges: Optional[int] = None) -> AIPlayer:
    templates = get_player_templates()
    template_map = {t.name: t for t in templates}

    if name in template_map:
        t = template_map[name]
        return AIPlayer(t.name, t.character, t.R, t.S, t.C, t.L,
                        is_human=is_human, max_charges=max_charges)
    if is_human:
        return AIPlayer(name, "人类玩家", 0.3, 0.5, 0.5, 0.05,
                        is_human=True, max_charges=max_charges)
    raise ValueError(f"Unknown player: {name}")


def create_game(player1_template: str, player2_template: str,
                human_player: Optional[str] = None,
                total_slots: int = DEFAULT_TOTAL_SLOTS,
                live_bullets: int = DEFAULT_LIVE_BULLETS,
                mode: str = DEFAULT_MODE,
                max_charges: int = DEFAULT_MAX_CHARGES,
                item_set: str = DEFAULT_ITEM_SET) -> GameSession:
    charges = max_charges if mode == "buckshot" else None
    p1 = create_player(player1_template, is_human=(human_player == player1_template),
                       max_charges=charges)
    p2 = create_player(player2_template, is_human=(human_player == player2_template),
                       max_charges=charges)
    return GameSession(p1, p2, total_slots=total_slots, live_bullets=live_bullets,
                       mode=mode, max_charges=max_charges, item_set=item_set)


def create_tournament(player_count: int = 6, total_slots: int = 6,
                      live_bullets: int = 1, seed: Optional[int] = None,
                      mode: str = DEFAULT_MODE,
                      max_charges: int = DEFAULT_MAX_CHARGES,
                      item_set: str = DEFAULT_ITEM_SET) -> RoundRobinRunner:
    return RoundRobinRunner(
        player_count=player_count,
        total_slots=total_slots,
        live_bullets=live_bullets,
        seed=seed,
        mode=mode,
        max_charges=max_charges,
        item_set=item_set,
    )
