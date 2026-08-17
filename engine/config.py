"""
AI 选手模板与游戏常量。

R=攻击阈值(p0超过R时倾向攻击) S=策略惯性(越高越重复上次选择)
C=冷静系数(越高越不受情绪影响) L=随机波动(决策噪音幅度)

SIGMOID_K=sigmoid锐度，越大切换越陡。K=4时R附近±0.3区间内完成自击→攻击转变。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DEFAULT_TOTAL_SLOTS = 6
DEFAULT_LIVE_BULLETS = 1
DEFAULT_PLAYER_COUNT = 6
SIGMOID_K = 4.0

# 恶魔轮盘（Buckshot Roulette）模式常量
DEFAULT_MODE = "classic"
VALID_MODES = ("classic", "buckshot", "duel")
BUCKSHOT_MIN_SHELLS = 2   # 每次装填的最少霰弹数
BUCKSHOT_MAX_SHELLS = 8   # 每次装填的最多霰弹数
DEFAULT_MAX_CHARGES = 3   # 默认生命电荷数

# 道具系统常量（Phase 2/3）
DEFAULT_ITEM_SET = "standard"   # buckshot 模式默认道具集
VALID_ITEM_SETS = ("none", "standard", "full")
STANDARD_ITEMS = ("magnifier", "beer", "cigarette", "handsaw", "handcuff")
# Double or Nothing 追加 4 件（Phase 3）
DON_ITEMS = ("inverter", "burner_phone", "expired_medicine", "adrenaline")
FULL_ITEMS = STANDARD_ITEMS + DON_ITEMS
ITEM_SLOT_CAP = 8        # 道具栏上限
ITEMS_PER_RELOAD = 2     # 每次装填（含开局）补发的道具数

# 过期药概率：50/50 起步（+2 电荷 / −1 电荷），可配置贴近原作体感
EXPIRED_MEDICINE_HEAL_CHANCE = 0.5


@dataclass(frozen=True)
class PlayerTemplate:
    """选手模板。R=攻击阈值, S=策略惯性, C=冷静系数, L=随机波动"""
    name: str
    character: str
    R: float
    S: float
    C: float
    L: float = 0.05


def get_player_templates(count: Optional[int] = None) -> list[PlayerTemplate]:
    templates = [
        PlayerTemplate("Claude", "谨慎稳定", 0.16, 0.65, 0.75, 0.02),
        PlayerTemplate("GPT", "理性中庸", 0.17, 0.50, 0.60, 0.04),
        PlayerTemplate("Kimi", "学习进化", 0.20, 0.45, 0.40, 0.08),
        PlayerTemplate("Gemini", "激情波动", 0.24, 0.30, 0.25, 0.10),
        PlayerTemplate("GLM", "随机不可测", 0.28, 0.10, 0.15, 0.18),
        PlayerTemplate("DeepSeek", "赌徒狂人", 0.32, 0.15, 0.20, 0.14),
    ]
    if count is None:
        return templates
    if count < 1:
        raise ValueError("count must be at least 1")
    if count > len(templates):
        raise ValueError("count cannot exceed the number of available templates")
    return templates[:count]
