"""对手建模（Theory of Mind · L2+，Phase 4）。

三个层次：
  信息层——对手经放大镜/反转器/电话获得的情报（道具使用本身公开可观察）
  行为层——贝叶斯反推：对手的射击选择泄露其隐藏情报
  威胁层——情报优势 × 道具栏 → 综合威胁评分，供效用内核与道具启发式消费

模型仅由公开信息驱动（道具栏、道具使用、射击行为、实/空配比均公开），
不含任何真实弹型泄露；重装时全量重置。每个玩家各持一个对对手的模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AIPlayer

# —— 行为贝叶斯系数 ——
# 对手使用手锯 → 几乎必然已知实弹（启发式门槛 1−0.6R ≥ 0.8）
P_KNOWS_LIVE_GIVEN_SAW = 0.9
# 对手高 p 自击却打空 → 强证据其持有空弹情报
HIGH_P_SELF_BLANK_INFO = 0.7
HIGH_P_SELF_BLANK_P_LIVE = 0.15
# 对手低 p 击敌 → 弱证据其实弹情报
LOW_P_ATTACK_INFO = 0.4
LOW_P_ATTACK_P_LIVE_LIFT = 0.25
LOW_P_ATTACK_P_LIVE_CAP = 0.85
# 行为证据阈值（射击前公开实弹概率）
HIGH_P = 0.65
LOW_P = 0.35
# 指针前移后行为证据衰减：指向的情报已被消费，对手可能还有电话接力
BEHAVIOR_DECAY = 0.6


@dataclass
class OpponentModel:
    """观察者视角下对对手私有情报的信念模型。"""

    peek_current: float = 0.0    # P(对手经放大镜/反转器确知当前弹)
    peek_live: float = 0.5       # P(其情报为实弹 | 已知)
    phone_pool: int = 0          # 电话查询时可选偏移上限（≈ 当时剩余弹数 − 1）
    phone_fired: int = 0         # 电话使用后指针前移次数
    has_phone: bool = False      # 对手本弹仓是否用过电话
    behavior_info: float = 0.0   # 行为反推：对手持有隐藏情报的信念

    def reset(self) -> None:
        self.peek_current = 0.0
        self.peek_live = 0.5
        self.phone_pool = 0
        self.phone_fired = 0
        self.has_phone = False
        self.behavior_info = 0.0

    # —— 信念读取 ——

    @property
    def phone_expired(self) -> float:
        """P(电话情报已到期成为当前弹知识)。查询偏移近似均匀分布于 [1, pool]。"""
        if not self.has_phone or self.phone_pool <= 0:
            return 0.0
        return min(self.phone_fired, self.phone_pool) / self.phone_pool

    def info_current(self) -> float:
        """P(对手已知当前弹型)——三个情报来源取最大。"""
        return min(1.0, max(self.peek_current, self.phone_expired,
                            self.behavior_info))

    def p_knows_live(self) -> float:
        """P(对手已知当前为实弹)。"""
        return self.info_current() * self.peek_live

    def p_knows_blank(self) -> float:
        """P(对手已知当前为空弹)。"""
        return self.info_current() * (1.0 - self.peek_live)

    # —— 观察接口 ——

    def observe_item(self, item_id: str, public_p_live: float,
                     phone_pool: int) -> None:
        """观察对手使用道具（道具使用公开）。public_p_live 为使用后公开实弹概率。"""
        if item_id == "magnifier":
            self.peek_current = 1.0
            self.peek_live = public_p_live
        elif item_id == "inverter":
            self.peek_current = 1.0
            self.peek_live = public_p_live   # 反转后公开配比已更新
        elif item_id == "burner_phone":
            self.has_phone = True
            self.phone_pool = max(1, phone_pool)
            self.phone_fired = 0
        elif item_id == "handsaw":
            self.peek_current = 1.0
            self.peek_live = max(self.peek_live, P_KNOWS_LIVE_GIVEN_SAW)

    def observe_shot(self, choice: str, was_live: bool,
                     public_p_live_before: float,
                     had_peek: bool = False) -> None:
        """观察对手射击行为，反推其隐藏情报。

        had_peek：对手射击前是否已确知当前弹（此时行为不新增证据）。
        调用顺序要求：on_advance 之后调用——旧证据已衰减，新证据不被本次消费打折。
        """
        if had_peek or self.peek_current >= 0.99:
            return
        if choice == "self" and not was_live and public_p_live_before >= HIGH_P:
            # 高 p 仍敢自击且打空：大概率握有空弹情报
            self.behavior_info = max(self.behavior_info, HIGH_P_SELF_BLANK_INFO)
            self.peek_live = min(self.peek_live, HIGH_P_SELF_BLANK_P_LIVE)
        elif choice == "opponent" and public_p_live_before <= LOW_P:
            # 低 p 仍果断击敌：可能握有实弹情报
            self.behavior_info = max(self.behavior_info, LOW_P_ATTACK_INFO)
            self.peek_live = min(LOW_P_ATTACK_P_LIVE_CAP,
                                 self.peek_live + LOW_P_ATTACK_P_LIVE_LIFT)

    def on_advance(self) -> None:
        """弹仓指针前移：放大镜类情报被消费，电话到期推进，行为证据衰减。"""
        self.peek_current = 0.0
        if self.has_phone:
            self.phone_fired += 1
        self.behavior_info *= BEHAVIOR_DECAY


def compute_threat(model: OpponentModel, opp: "AIPlayer",
                   my_charges: int | None = None) -> float:
    """综合威胁 ∈ [0,1]：对手把情报优势转化为重击的即时能力。

    damage：实弹情报 × 手锯在场（已磨锯或栏里有锯）
    tempo：情报优势 × 手铐（锁我方后连续行动）
    finisher：我方濒死且对手已磨锯——斩首窗口
    """
    info = model.info_current()
    knows_live = model.p_knows_live()

    saw_ready = opp.sawed or ("handsaw" in opp.items)
    damage = knows_live * (1.0 if saw_ready else 0.7)
    tempo = info * (0.6 if "handcuff" in opp.items else 0.2)

    threat = 0.65 * damage + 0.25 * tempo
    if my_charges is not None and my_charges <= 2 and opp.sawed:
        threat += 0.25
    return max(0.0, min(1.0, threat))
