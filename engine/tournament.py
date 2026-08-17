from __future__ import annotations

import random
import uuid
from abc import ABC, abstractmethod
from itertools import combinations
from typing import Optional

from .config import (DEFAULT_PLAYER_COUNT, DEFAULT_TOTAL_SLOTS, DEFAULT_LIVE_BULLETS,
                     DEFAULT_MODE, DEFAULT_MAX_CHARGES, DEFAULT_ITEM_SET,
                     get_player_templates)
from .game import GameSession
from .models import AIPlayer


class BaseRunner(ABC):
    """锦标赛基类 — 定义统一接口，便于扩展不同赛制"""

    def __init__(self, player_count: int, total_slots: int, live_bullets: int,
                 seed: Optional[int] = None, mode: str = DEFAULT_MODE,
                 max_charges: int = DEFAULT_MAX_CHARGES,
                 item_set: str = DEFAULT_ITEM_SET):
        # 使用独立 rng，避免污染进程级全局随机状态
        self._rng = random.Random(seed)

        self.id = uuid.uuid4().hex[:8]
        self.mode = mode
        self.max_charges = max_charges
        self.item_set = item_set
        self.total_slots = total_slots
        self.live_bullets = live_bullets
        self.is_over = False
        self.ranking: list[dict] = []

    @abstractmethod
    def get_state(self) -> dict:
        ...

    @abstractmethod
    def step(self) -> dict:
        ...

    @abstractmethod
    def run_all(self) -> dict:
        ...


class RoundRobinRunner(BaseRunner):
    """循环赛：每个选手与其他选手各打一场，按胜场排名"""

    def __init__(self, player_count=DEFAULT_PLAYER_COUNT, total_slots=DEFAULT_TOTAL_SLOTS,
                 live_bullets=DEFAULT_LIVE_BULLETS, seed: Optional[int] = None,
                 mode: str = DEFAULT_MODE, max_charges: int = DEFAULT_MAX_CHARGES,
                 item_set: str = DEFAULT_ITEM_SET):
        super().__init__(player_count, total_slots, live_bullets, seed,
                         mode=mode, max_charges=max_charges, item_set=item_set)

        templates = get_player_templates(count=player_count)
        self.players = [AIPlayer(t.name, t.character, t.R, t.S, t.C, t.L,
                                 max_charges=(max_charges if mode == "buckshot" else None))
                        for t in templates]

        num_players = len(self.players)
        pairs = list(combinations(range(num_players), 2))
        self._rng.shuffle(pairs)
        self.schedule: list[tuple[int, int]] = []
        for idx_a, idx_b in pairs:
            if self._rng.random() < 0.5:
                self.schedule.append((idx_b, idx_a))
            else:
                self.schedule.append((idx_a, idx_b))

        self.num_players = num_players
        self.wins = [0] * num_players
        self.losses = [0] * num_players
        self.kills = [0] * num_players
        self.match_index = 0
        self.total_matches = len(self.schedule)
        self.current_game: Optional[GameSession] = None
        self.match_results: list[dict] = []

    def get_state(self) -> dict:
        return {
            "id": self.id,
            "mode": self.mode,
            "item_set": self.item_set,
            "players": [p.to_dict() for p in self.players],
            "schedule": [{"p1": self.players[idx_a].name, "p2": self.players[idx_b].name}
                         for idx_a, idx_b in self.schedule],
            "total_matches": self.total_matches,
            "match_index": self.match_index,
            "is_over": self.is_over,
            "wins": self.wins,
            "losses": self.losses,
            "kills": self.kills,
            "ranking": self.ranking,
            "match_results": self.match_results,
            "current_game": self.current_game.get_state() if self.current_game else None,
        }

    def step(self) -> dict:
        if self.is_over:
            return self.get_state()

        if self.match_index >= self.total_matches:
            self._compute_ranking()
            return self.get_state()

        idx_a, idx_b = self.schedule[self.match_index]
        p1, p2 = self.players[idx_a], self.players[idx_b]

        game = GameSession(p1, p2, total_slots=self.total_slots,
                           live_bullets=self.live_bullets, mode=self.mode,
                           max_charges=self.max_charges, item_set=self.item_set,
                           rng=self._rng)
        game.auto_play_to_end()

        if game.winner is p1:
            self.wins[idx_a] += 1
            self.losses[idx_b] += 1
        else:
            self.wins[idx_b] += 1
            self.losses[idx_a] += 1

        # 从游戏事件中统计真实击杀（射中对手实弹），自杀不计
        for event in game.events:
            if event.type == "fire" and event.is_live and event.action == "opponent":
                if event.player_name == p1.name:
                    self.kills[idx_a] += 1
                else:
                    self.kills[idx_b] += 1

        result = {
            "match_num": self.match_index + 1,
            "p1": p1.name,
            "p2": p2.name,
            "winner": game.winner.name if game.winner else None,
            "events": [e.to_dict() for e in game.events],
        }
        self.match_results.append(result)
        self.current_game = game
        self.match_index += 1

        if self.match_index >= self.total_matches:
            self._compute_ranking()

        return self.get_state()

    def run_all(self) -> dict:
        while self.match_index < self.total_matches:
            self.step()
        return self.get_state()

    def _compute_ranking(self):
        self.is_over = True
        sorted_indices = sorted(
            range(self.num_players),
            key=lambda idx: self.wins[idx],
            reverse=True,
        )
        # 并列排名：同胜场同排名
        self.ranking = []
        current_rank = 1
        prev_wins = None
        for rank_pos, player_idx in enumerate(sorted_indices):
            if prev_wins is not None and self.wins[player_idx] != prev_wins:
                current_rank = rank_pos + 1
            self.ranking.append({
                "rank": current_rank,
                "name": self.players[player_idx].name,
                "character": self.players[player_idx].character,
                "wins": self.wins[player_idx],
                "losses": self.losses[player_idx],
                "kills": self.kills[player_idx],
            })
            prev_wins = self.wins[player_idx]
