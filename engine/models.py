from __future__ import annotations

import random
from typing import Optional

from .config import BUCKSHOT_MIN_SHELLS, BUCKSHOT_MAX_SHELLS
from .theory import OpponentModel


class AIPlayer:
    """AI 选手。R=风险感知, S=策略惯性, C=冷静系数, L=随机波动; M∈[-1,1] 为实时心态

    max_charges=None 表示经典模式（一枪定生死）；恶魔轮盘模式下为生命电荷制。
    """

    def __init__(self, name: str, character: str, R: float, S: float, C: float,
                 L: float = 0.05, is_human: bool = False,
                 max_charges: Optional[int] = None):
        self.name = name
        self.character = character
        self.R = R
        self.S = S
        self.C = C
        self.L = L
        self.M: float = 0.0
        self.is_alive: bool = True
        self.is_human: bool = is_human
        self.max_charges = max_charges
        self.charges: Optional[int] = max_charges
        self.last_choice: Optional[str] = None
        self.win_streak: int = 0
        self.loss_streak: int = 0
        self.last_result: Optional[str] = None
        self.last_opponent: Optional[str] = None
        # —— 道具系统（恶魔轮盘 Phase 2）——
        self.items: list[str] = []
        self.known_shells: dict[int, bool] = {}   # 私有信息集：弹位偏移(0=当前弹)→弹型
        self.sawed: bool = False       # 手锯：下次实弹伤害 ×2（公开状态）
        self.skip_next: bool = False   # 手铐：下回合被跳过（公开状态）
        self.last_cuffed: Optional[str] = None    # 上一次手铐目标（不可连续铐同一人）
        # —— 对手建模（Phase 4 L2+）——
        self.opp_model = OpponentModel()          # 对对手私有情报的信念模型

    def prepare_for_match(self, opponent_name: Optional[str] = None) -> 'AIPlayer':
        self.is_alive = True
        self.last_choice = None
        if self.max_charges is not None:
            self.charges = self.max_charges
        self.M *= 0.7
        self.items = []
        self.known_shells = {}
        self.sawed = False
        self.skip_next = False
        self.last_cuffed = None
        self.opp_model.reset()
        return self

    def take_damage(self, amount: int = 1) -> bool:
        """扣除电荷。返回 True 表示被击倒（恶魔轮盘模式专用）。"""
        if self.charges is None:
            self.charges = 0
        self.charges = max(0, self.charges - amount)
        if self.charges <= 0:
            self.is_alive = False
        return self.charges <= 0

    def heal(self, amount: int = 1) -> int:
        """回复电荷（不超上限）。返回实际回复量。"""
        if self.charges is None or self.max_charges is None:
            return 0
        before = self.charges
        self.charges = min(self.max_charges, self.charges + amount)
        return self.charges - before

    def advance_known(self) -> None:
        """弹仓指针前移后重映射私有信息集：offset 0 已消耗，其余整体前移。"""
        self.known_shells = {k - 1: v for k, v in self.known_shells.items() if k > 0}

    def update_mindset(self, event: str, opponent: Optional['AIPlayer'] = None) -> None:
        if event == "win":
            self.win_streak += 1
            self.loss_streak = 0
            self.M = min(1.0, self.M + 0.08 + 0.02 * self.win_streak)
            self.last_result = "win"
        elif event == "loss":
            self.loss_streak += 1
            self.win_streak = 0
            self.M = max(-1.0, self.M - (0.10 + 0.03 * self.loss_streak))
            self.last_result = "loss"
        elif event == "rest":
            self.M *= 0.8

        if opponent is not None:
            self.last_opponent = getattr(opponent, "name", opponent)

        self.M = max(-1.0, min(1.0, self.M))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "character": self.character,
            "R": self.R,
            "S": self.S,
            "C": self.C,
            "L": self.L,
            "M": round(self.M, 3),
            "is_alive": self.is_alive,
            "is_human": self.is_human,
            "last_choice": self.last_choice,
            "win_streak": self.win_streak,
            "loss_streak": self.loss_streak,
            "charges": self.charges,
            "max_charges": self.max_charges,
            "items": list(self.items),
            "known_shells": dict(self.known_shells),
            "sawed": self.sawed,
            "skip_next": self.skip_next,
        }


class RouletteGun:
    """左轮手枪。chamber 内随机分布实弹，pointer 依次击发，打空自动重装"""

    def __init__(self, total_slots: int = 6, live_bullets: int = 1,
                 rng: Optional[random.Random] = None):
        if live_bullets < 1:
            raise ValueError("live_bullets must be at least 1")
        if live_bullets > total_slots:
            raise ValueError("live_bullets cannot exceed total_slots")
        self.total_slots = total_slots
        self.live_bullets = live_bullets
        self._rng = rng if rng is not None else random
        self.chamber = [False] * total_slots
        indices = self._rng.sample(range(total_slots), live_bullets)
        for idx in indices:
            self.chamber[idx] = True
        self.pointer = 0

    def get_p0(self) -> float:
        remaining_slots = self.total_slots - self.pointer
        if remaining_slots <= 0:
            return 0.0
        remaining_live = sum(self.chamber[self.pointer:])
        return remaining_live / remaining_slots

    def shoot(self) -> bool:
        if self.pointer >= self.total_slots:
            raise RuntimeError("No remaining slots in the chamber")
        is_live = self.chamber[self.pointer]
        self.pointer += 1
        return is_live

    def reload(self) -> None:
        self.chamber = [False] * self.total_slots
        indices = self._rng.sample(range(self.total_slots), self.live_bullets)
        for idx in indices:
            self.chamber[idx] = True
        self.pointer = 0

    def get_remaining(self) -> tuple[int, int]:
        remaining_slots = self.total_slots - self.pointer
        remaining_live = sum(self.chamber[self.pointer:])
        return remaining_live, remaining_slots

    def to_dict(self) -> dict:
        remaining_live, remaining_slots = self.get_remaining()
        return {
            "total_slots": self.total_slots,
            "live_bullets": self.live_bullets,
            "pointer": self.pointer,
            "remaining_live": remaining_live,
            "remaining_slots": remaining_slots,
        }


class Shotgun:
    """霰弹枪（恶魔轮盘模式）。每次装填 2-8 发、实空配比随机且数量公开、顺序保密。

    与 RouletteGun 的关键差异：容量与配比逐次随机（重装即换新比例），
    空弹占比公开可知，弹型顺序仍保密——这是恶魔轮盘推理博弈的基础。
    """

    def __init__(self, min_shells: int = BUCKSHOT_MIN_SHELLS,
                 max_shells: int = BUCKSHOT_MAX_SHELLS,
                 rng: Optional[random.Random] = None):
        if min_shells < 2:
            raise ValueError("min_shells must be at least 2")
        if max_shells < min_shells:
            raise ValueError("max_shells cannot be smaller than min_shells")
        self.min_shells = min_shells
        self.max_shells = max_shells
        self._rng = rng if rng is not None else random
        self.reload()

    def reload(self) -> None:
        """随机装填：总量 ∈ [min, max]，实弹数 ∈ [1, total-1]，保证实空各至少一发。"""
        self.total_slots = self._rng.randint(self.min_shells, self.max_shells)
        live = self._rng.randint(1, self.total_slots - 1)
        self.live_bullets = live
        self.blank_bullets = self.total_slots - live
        self.chamber = [True] * live + [False] * self.blank_bullets
        self._rng.shuffle(self.chamber)
        self.pointer = 0

    @property
    def is_empty(self) -> bool:
        return self.pointer >= self.total_slots

    def peek(self) -> bool:
        """查看当前弹型但不击发（放大镜原语，Phase 2）。"""
        if self.is_empty:
            raise RuntimeError("No remaining shells in the shotgun")
        return self.chamber[self.pointer]

    def peek_at(self, offset: int) -> bool:
        """查看距当前弹 offset 发位置的弹型（电话原语，Phase 3）。offset ≥ 1。"""
        idx = self.pointer + offset
        if offset < 1 or idx >= self.total_slots:
            raise IndexError(f"offset out of range: {offset}")
        return self.chamber[idx]

    def invert(self) -> bool:
        """反转当前弹：实↔空互换（反转器原语，Phase 3）。返回反转后的弹型。"""
        if self.is_empty:
            raise RuntimeError("No remaining shells in the shotgun")
        self.chamber[self.pointer] = not self.chamber[self.pointer]
        if self.chamber[self.pointer]:
            self.live_bullets += 1
            self.blank_bullets -= 1
        else:
            self.live_bullets -= 1
            self.blank_bullets += 1
        return self.chamber[self.pointer]

    def eject(self) -> bool:
        """退掉当前弹并公开其类型（啤酒原语）。返回被退出的弹型，pointer 前移。"""
        if self.is_empty:
            raise RuntimeError("No remaining shells in the shotgun")
        shell = self.chamber[self.pointer]
        self.pointer += 1
        return shell

    def get_p0(self) -> float:
        remaining_live, remaining_slots = self.get_remaining()
        if remaining_slots <= 0:
            return 0.0
        return remaining_live / remaining_slots

    def shoot(self) -> bool:
        if self.is_empty:
            raise RuntimeError("No remaining shells in the shotgun")
        is_live = self.chamber[self.pointer]
        self.pointer += 1
        return is_live

    def get_remaining(self) -> tuple[int, int]:
        remaining_slots = self.total_slots - self.pointer
        remaining_live = sum(self.chamber[self.pointer:])
        return remaining_live, remaining_slots

    def get_counts(self) -> tuple[int, int]:
        """公开信息：剩余 (实弹数, 空弹数)。"""
        remaining_live, remaining_slots = self.get_remaining()
        return remaining_live, remaining_slots - remaining_live

    def to_dict(self) -> dict:
        remaining_live, remaining_blank = self.get_counts()
        remaining_slots = remaining_live + remaining_blank
        return {
            "total_slots": self.total_slots,
            "live_bullets": remaining_live,
            "blank_bullets": remaining_blank,
            "pointer": self.pointer,
            "remaining_live": remaining_live,
            "remaining_blank": remaining_blank,
            "remaining_slots": remaining_slots,
        }
