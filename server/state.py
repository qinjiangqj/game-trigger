from __future__ import annotations

import asyncio
import time
from typing import Optional

from engine.game import GameSession
from engine.tournament import BaseRunner

GAME_TTL = 3600  # 1 小时后自动清理

games: dict[str, tuple[GameSession, float]] = {}
tournaments: dict[str, tuple[BaseRunner, float]] = {}


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(300)  # 每 5 分钟扫描一次
        now = time.time()
        for gid in list(games.keys()):
            if now - games[gid][1] > GAME_TTL:
                del games[gid]
        for tid in list(tournaments.keys()):
            if now - tournaments[tid][1] > GAME_TTL:
                del tournaments[tid]


def add_game(game: GameSession) -> None:
    games[game.id] = (game, time.time())


def get_game(game_id: str) -> Optional[GameSession]:
    entry = games.get(game_id)
    if entry is None:
        return None
    # 活跃访问续期时间戳，避免进行中的会话被 TTL 误删
    games[game_id] = (entry[0], time.time())
    return entry[0]


def add_tournament(tournament: BaseRunner) -> None:
    tournaments[tournament.id] = (tournament, time.time())


def get_tournament(tournament_id: str) -> Optional[BaseRunner]:
    entry = tournaments.get(tournament_id)
    if entry is None:
        return None
    tournaments[tournament_id] = (entry[0], time.time())
    return entry[0]
