from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CreateGameRequest(BaseModel):
    """创建对局请求"""
    player1: str = Field(min_length=1, max_length=32)
    player2: str = Field(min_length=1, max_length=32)
    human_player: Optional[str] = None
    total_slots: int = Field(default=6, ge=2, le=12)
    live_bullets: int = Field(default=1, ge=1, le=12)
    mode: Literal["classic", "buckshot", "duel"] = "classic"
    max_charges: int = Field(default=3, ge=1, le=8)
    item_set: Literal["none", "standard", "full"] = "standard"

    @model_validator(mode="after")
    def check_bullets(self):
        if self.mode in ("classic", "duel") and self.live_bullets > self.total_slots:
            raise ValueError("live_bullets cannot exceed total_slots")
        # 非恶魔轮盘模式无道具：与引擎归一规则一致（GameSession 强制 none）
        if self.mode != "buckshot":
            self.item_set = "none"
        return self


class HumanActionRequest(BaseModel):
    """人类玩家行动请求（双形态）：射击 choice 或道具 item_id，二选一。

    {"choice": "self"|"opponent"}        射击自己/对方（消耗回合）
    {"item_id": "magnifier"|...}         使用道具（不消耗回合，仍需射击）
    """
    choice: Optional[Literal["self", "opponent"]] = None
    item_id: Optional[str] = Field(default=None, min_length=1, max_length=24)

    @model_validator(mode="after")
    def check_exactly_one(self):
        if (self.choice is None) == (self.item_id is None):
            raise ValueError("choice 与 item_id 必须提供且只能提供一个")
        return self


class CreateTournamentRequest(BaseModel):
    """创建锦标赛请求"""
    player_count: int = Field(default=6, ge=2, le=6)
    total_slots: int = Field(default=6, ge=2, le=12)
    live_bullets: int = Field(default=1, ge=1, le=12)
    seed: Optional[int] = None
    mode: Literal["classic", "buckshot", "duel"] = "classic"
    max_charges: int = Field(default=3, ge=1, le=8)
    item_set: Literal["none", "standard", "full"] = "standard"

    @model_validator(mode="after")
    def check_bullets(self):
        if self.mode in ("classic", "duel") and self.live_bullets > self.total_slots:
            raise ValueError("live_bullets cannot exceed total_slots")
        if self.mode != "buckshot":
            self.item_set = "none"
        return self
