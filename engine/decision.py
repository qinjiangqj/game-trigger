from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

from .config import SIGMOID_K
from .items import ITEM_REGISTRY, check_usable, unknown_phone_offsets
from .models import AIPlayer, RouletteGun, Shotgun
from .theory import compute_threat

# 蝉联期权系数：scale × R × (1-p0) 从攻击倾向中扣除
# R 越高(赌徒)→期权越大→更愿自击博蝉联；R 越低(谨慎)→期权越小→不受影响
OPTION_SCALE = 0.15


@dataclass
class AttackBreakdown:
    """决策明细。pr 为存活感知，base_attack 为攻击倾向"""
    s_real: float
    reanalyzed: bool
    pr: float
    base_attack: float
    option_value: float
    mindset_delta: float
    attack_after_mindset: float
    calm_delta: float
    attack_after_calm: float
    random_delta: float
    final_attack: float
    choice: str

    def to_dict(self) -> dict:
        return {
            "s_real": round(self.s_real, 3),
            "reanalyzed": self.reanalyzed,
            "pr": round(self.pr, 3),
            "base_attack": round(self.base_attack, 3),
            "option_value": round(self.option_value, 3),
            "mindset_delta": round(self.mindset_delta, 3),
            "attack_after_mindset": round(self.attack_after_mindset, 3),
            "calm_delta": round(self.calm_delta, 3),
            "attack_after_calm": round(self.attack_after_calm, 3),
            "random_delta": round(self.random_delta, 3),
            "final_attack": round(self.final_attack, 3),
            "choice": self.choice,
        }


def _apply_modifiers(ai: AIPlayer, base_attack: float, low_clamp: float = 0.0,
                     rng: Optional[random.Random] = None) -> AttackBreakdown:
    """心态→冷静→随机 三阶段修正，返回 AttackBreakdown 的中间字段填充。"""
    _rng = rng if rng is not None else random
    mindset_delta = ai.M * 0.25
    attack_after_mindset = base_attack + mindset_delta

    emotion = abs(ai.M)
    calm_factor = max(0.0, 1.0 - ai.C * emotion)
    calm_delta = attack_after_mindset * (calm_factor - 1.0)
    attack_after_calm = attack_after_mindset * calm_factor

    random_delta = _rng.uniform(-ai.L, ai.L)
    final_attack = max(low_clamp, min(1.0, attack_after_calm + random_delta))

    return AttackBreakdown(
        s_real=0,
        reanalyzed=True,
        pr=0,
        base_attack=base_attack,
        option_value=0,
        mindset_delta=mindset_delta,
        attack_after_mindset=attack_after_mindset,
        calm_delta=calm_delta,
        attack_after_calm=attack_after_calm,
        random_delta=random_delta,
        final_attack=final_attack,
        choice="",
    )


def make_decision(ai: AIPlayer, p0: float, opponent_name: str,
                  rng: Optional[random.Random] = None) -> tuple[str, AttackBreakdown]:
    _rng = rng if rng is not None else random
    # 惯性随 p0 上升衰减：越危险越不能靠习惯，必须重新分析
    s_real = max(0.0, ai.S * (1.0 - p0) - 0.05 * ai.loss_streak)

    if ai.last_choice is not None and _rng.random() < s_real:
        return ai.last_choice, AttackBreakdown(
            s_real=s_real, reanalyzed=False,
            pr=0, base_attack=0, option_value=0,
            mindset_delta=0,
            attack_after_mindset=0, calm_delta=0,
            attack_after_calm=0, random_delta=0,
            final_attack=0, choice=ai.last_choice,
        )

    if p0 <= 0:
        # 弹巢全空，射自己必蝉联。攻击倾向=0，存活感知=100%
        choice = "self"
        ai.last_choice = choice
        return choice, AttackBreakdown(
            s_real=s_real, reanalyzed=True,
            pr=1.0, base_attack=0.0, option_value=0.0,
            mindset_delta=0.0,
            attack_after_mindset=0.0,
            calm_delta=0.0,
            attack_after_calm=0.0,
            random_delta=0.0,
            final_attack=0.0,
            choice=choice,
        )

    if p0 >= 1:
        # 仅剩实弹，自击等同自杀，强制攻击
        base_attack = 1.0
        pr = 0.0
        option_value = 0.0
    else:
        # sigmoid: R=攻击阈值(p0>R则倾向攻击), K=4.0 控制切换锐度
        raw_base = 1.0 / (1.0 + math.exp(-SIGMOID_K * (p0 - ai.R)))
        # 蝉联期权：自击空枪后保留回合权。R 越高越看重蝉联价值
        # option = scale × R × (1-p0)，赌徒期权大、谨慎者期权小
        option_value = OPTION_SCALE * ai.R * (1.0 - p0)
        base_attack = max(0.02, raw_base - option_value)
        pr = 1.0 - base_attack

    low_clamp = 0.51 if p0 >= 1 else 0.0
    bd = _apply_modifiers(ai, base_attack, low_clamp, rng=_rng)

    choice = "opponent" if bd.final_attack > 0.5 else "self"
    ai.last_choice = choice

    bd.s_real = s_real
    bd.pr = pr
    bd.option_value = option_value
    bd.choice = choice
    return choice, bd


# ==================== 恶魔轮盘模式：效用评估决策（§6 L1 内核） ====================

# 蝉联时机价值 T = BASE + CERTAINTY×确定性 + COMEBACK×落后度
# 确定性 |2p-1| 越高 → 当前弹型越可测 → 行动权越值钱
T_BASE = 0.5
T_CERTAINTY = 0.3
T_COMEBACK = 0.25
# 相等局面的人格偏置：R 低（谨慎）偏攻击保命，R 高（赌徒）偏自击博蝉联
TIE_BIAS_SCALE = 0.6
# 噪声作用于效用差（差值量级通常 0.2~1.5），故缩放 0.5
NOISE_SCALE = 0.5
# 威胁偏置（Phase 4 L2+）：对手威胁越高越倾向击敌抢回节奏，C 调制信任度
THREAT_BIAS = 0.4


@dataclass
class ShotBreakdown:
    """效用决策明细。diff>0 → 击敌，diff<0 → 自击"""
    s_real: float
    reanalyzed: bool
    p_live: float
    t_value: float
    tie_bias: float
    lam_kill: float
    lam_own: float
    lam_give: float
    eu_self: float
    eu_enemy: float
    raw_diff: float
    mindset_delta: float
    calm_factor: float
    noise_delta: float
    final_diff: float
    choice: str
    opp_threat: float = 0.0    # 对手威胁评估（公开信息推断，Phase 4）
    threat_bias: float = 0.0   # 威胁偏置贡献

    def to_dict(self) -> dict:
        return {
            "kernel": "utility",
            "s_real": round(self.s_real, 3),
            "reanalyzed": self.reanalyzed,
            "p_live": round(self.p_live, 3),
            "t_value": round(self.t_value, 3),
            "tie_bias": round(self.tie_bias, 3),
            "lam_kill": round(self.lam_kill, 3),
            "lam_own": round(self.lam_own, 3),
            "lam_give": round(self.lam_give, 3),
            "eu_self": round(self.eu_self, 3),
            "eu_enemy": round(self.eu_enemy, 3),
            "raw_diff": round(self.raw_diff, 3),
            "mindset_delta": round(self.mindset_delta, 3),
            "calm_factor": round(self.calm_factor, 3),
            "noise_delta": round(self.noise_delta, 3),
            "final_diff": round(self.final_diff, 3),
            "choice": self.choice,
            "opp_threat": round(self.opp_threat, 3),
            "threat_bias": round(self.threat_bias, 3),
        }


def make_utility_decision(ai: AIPlayer, p_live: float, my_charges: int,
                          opp_charges: int, dmg: int = 1,
                          rng: Optional[random.Random] = None,
                          opp_threat: float = 0.0) -> tuple[str, ShotBreakdown]:
    """恶魔轮盘射击决策：比较 EU(自击) 与 EU(击敌)，人格调制作用于效用差。

    EU(self)  = (1-p)·T          +  p·(-dmg·λ_own)
    EU(enemy) = p·(dmg·λ_kill)   +  (1-p)·(-T·λ_give)
    λ 由 R 派生：R 低 → λ_kill 高（攻击保命型）；R 高 → λ_own/give 高（赌自击蝉联型）
    opp_threat：对手威胁评估（L2+）——威胁越高越倾向击敌抢回行动权，C 调制信任度
    """
    _rng = rng if rng is not None else random
    threat_bias = ai.C * THREAT_BIAS * opp_threat

    # —— 惯性判定（与经典模式同构）——
    s_real = max(0.0, ai.S * (1.0 - p_live) - 0.05 * ai.loss_streak)
    if ai.last_choice is not None and _rng.random() < s_real:
        return ai.last_choice, ShotBreakdown(
            s_real=s_real, reanalyzed=False,
            p_live=p_live, t_value=0, tie_bias=0,
            lam_kill=0, lam_own=0, lam_give=0,
            eu_self=0, eu_enemy=0, raw_diff=0,
            mindset_delta=0, calm_factor=1.0, noise_delta=0,
            final_diff=0, choice=ai.last_choice,
            opp_threat=opp_threat, threat_bias=threat_bias,
        )

    lam_kill = 1.5 - 2.0 * ai.R
    lam_own = 0.8 + 1.2 * ai.R
    lam_give = 0.5 + 0.8 * ai.R

    # —— 边界情形 ——
    if p_live <= 0:
        choice = "self"  # 已知空弹：自击必蝉联，严格占优
        ai.last_choice = choice
        return choice, ShotBreakdown(
            s_real=s_real, reanalyzed=True,
            p_live=0, t_value=1.0, tie_bias=0,
            lam_kill=lam_kill, lam_own=lam_own, lam_give=lam_give,
            eu_self=1.0, eu_enemy=-lam_give, raw_diff=1.0 + lam_give,
            mindset_delta=0, calm_factor=1.0, noise_delta=0,
            final_diff=1.0 + lam_give, choice=choice,
        )
    if p_live >= 1:
        choice = "opponent"  # 已知实弹：自击等同自残，强制攻击
        ai.last_choice = choice
        return choice, ShotBreakdown(
            s_real=s_real, reanalyzed=True,
            p_live=1, t_value=0, tie_bias=0,
            lam_kill=lam_kill, lam_own=lam_own, lam_give=lam_give,
            eu_self=-dmg * lam_own, eu_enemy=dmg * lam_kill,
            raw_diff=dmg * (lam_kill + lam_own),
            mindset_delta=0, calm_factor=1.0, noise_delta=0,
            final_diff=dmg * (lam_kill + lam_own), choice=choice,
        )

    # —— 蝉联时机价值 T ——
    certainty = abs(2.0 * p_live - 1.0)                      # 弹型越可测行动权越值钱
    charge_lead = (opp_charges - my_charges) / max(my_charges, opp_charges, 1)
    t_value = T_BASE + T_CERTAINTY * certainty + T_COMEBACK * charge_lead

    eu_self = (1.0 - p_live) * t_value + p_live * (-dmg * lam_own)
    eu_enemy = p_live * (dmg * lam_kill) + (1.0 - p_live) * (-t_value * lam_give)

    tie_bias = (0.25 - ai.R) * TIE_BIAS_SCALE
    threat_bias = ai.C * THREAT_BIAS * opp_threat
    raw_diff = eu_enemy - eu_self + tie_bias + threat_bias

    # —— 人格调制链：心态 → 冷静 → 噪声（作用于效用差）——
    mindset_delta = ai.M * 0.25
    after_mindset = raw_diff + mindset_delta

    emotion = abs(ai.M)
    calm_factor = max(0.0, 1.0 - ai.C * emotion)
    after_calm = after_mindset * calm_factor

    noise_delta = _rng.uniform(-ai.L, ai.L) * NOISE_SCALE
    final_diff = after_calm + noise_delta

    choice = "opponent" if final_diff > 0 else "self"
    ai.last_choice = choice

    return choice, ShotBreakdown(
        s_real=s_real, reanalyzed=True,
        p_live=p_live, t_value=t_value, tie_bias=tie_bias,
        lam_kill=lam_kill, lam_own=lam_own, lam_give=lam_give,
        eu_self=eu_self, eu_enemy=eu_enemy, raw_diff=raw_diff,
        mindset_delta=mindset_delta, calm_factor=calm_factor,
        noise_delta=noise_delta, final_diff=final_diff, choice=choice,
        opp_threat=opp_threat, threat_bias=threat_bias,
    )


# ==================== 道具阶段：信息融合 + 使用启发式（Phase 2） ====================

def fuse_p_live(gun: Shotgun, player: AIPlayer) -> float:
    """融合公开计数与私有信息集：已知当前弹型则取 0/1，否则用公开比例。"""
    if 0 in player.known_shells:
        return 1.0 if player.known_shells[0] else 0.0
    remaining_live, remaining_slots = gun.get_remaining()
    if remaining_slots <= 0:
        return 0.0
    return remaining_live / remaining_slots


def next_item_action(ai: AIPlayer, gun: Shotgun, opp: AIPlayer,
                     rng: Optional[random.Random] = None,
                     attempted: Optional[set[str]] = None) -> Optional[str]:
    """道具使用启发式（Phase 2 简化版）。

    返回下一个要用的道具 id；None 表示道具阶段结束，进入射击。
    attempted 为本阶段已尝试过的道具集合：每个道具每次道具阶段只掷骰一次，
    防止外层循环重试把人格概率磨平成"必然使用"。
    设计原则（§6）：
      放大镜——不确定性高才看；冷静求证(C)为主、惯性(S)为辅
      电话——侦察未来弹，弹仓越长价值越大
      反转器——已知实弹反空白嫖回合 / 低 p 反转赌实弹收尾（赌徒）
      过期药——EV+0.5 有方差；濒死赌命是赌徒专属
      肾上腺素——对方有高价值道具时偷取连招
      啤酒——p 接近 0.5 时信息价值最大，弹型极端时几乎无价值
      香烟——边际生命价值：电荷落后必用，满血禁用（硬校验拦截）
      手锯——已知当前为实弹且即将击敌；R 低更果断
      手铐——对方低电荷收尾 / 我方信息优势；C 高者优先
    """
    _rng = rng if rng is not None else random
    remaining_live, remaining_slots = gun.get_remaining()
    remaining_blank = remaining_slots - remaining_live

    for item_id in ai.items:
        if item_id not in ITEM_REGISTRY:
            continue
        if attempted is not None and item_id in attempted:
            continue
        if check_usable(item_id, ai, gun, opp) is not None:
            continue

        def _draw(p: float) -> bool:
            """单次人格掷骰；失败则记入 attempted，本阶段不再重试。"""
            if _rng.random() < p:
                return True
            if attempted is not None:
                attempted.add(item_id)
            return False

        if item_id == "magnifier":
            if remaining_live >= 1 and remaining_blank >= 1:
                # 信息欲 = 冷静求证(C)为主 + 打破惯性(1-S)为辅：
                # 谨慎人格多侦察，惯性人格少动脑
                p_use = 0.15 + 0.85 * (0.35 * (1.0 - ai.S) + 0.65 * ai.C)
                if _draw(p_use):
                    return item_id
        elif item_id == "burner_phone":
            # 电话：侦察未来弹。弹仓越长信息价值越大；人格调制同放大镜略降
            if remaining_slots >= 3 and unknown_phone_offsets(ai, gun):
                p_use = 0.10 + 0.75 * (0.35 * (1.0 - ai.S) + 0.65 * ai.C)
                if _draw(p_use):
                    return item_id
        elif item_id == "inverter":
            # 反转器两种用法：
            #  a) 已知当前为实弹 → 反转成空弹，自击白嫖回合（高价值稳招）
            #  b) 实弹占比低且对方残血 → 反转赌实弹收尾（赌徒偏好）
            if ai.known_shells.get(0) is True:
                if _draw(0.55 + 0.35 * ai.C):
                    return item_id
            elif (remaining_live >= 1 and remaining_blank >= 1
                  and (opp.charges or 1) <= 2 and fuse_p_live(gun, ai) <= 0.5):
                if _draw(0.2 + 0.6 * ai.R):
                    return item_id
        elif item_id == "expired_medicine":
            # 过期药 EV=+0.5 但有方差；濒死时是五五开赌命（赌徒专属）
            if ai.charges is not None and ai.charges == 1:
                if _draw(0.75 * ai.R):
                    return item_id
            elif ai.charges is not None and ai.charges < (ai.max_charges or 0):
                if _draw(0.15 + 0.35 * ai.R):
                    return item_id
        elif item_id == "adrenaline":
            # 肾上腺素：对方有高价值道具可偷时用；冷静者把握时机更准
            stealable = [i for i in opp.items if i != "adrenaline"]
            if stealable:
                if _draw(0.35 + 0.4 * ai.C):
                    return item_id
        elif item_id == "beer":
            if 0 in ai.known_shells:
                continue  # 已知当前弹型：退弹反而浪费确定性
            # L2 防御退弹（Phase 4）：对手握实弹情报且有锯——退弹销毁其确定性连招
            if (ai.opp_model.p_knows_live() >= 0.55
                    and (opp.sawed or "handsaw" in opp.items)):
                if _draw(0.5 + 0.4 * ai.C):
                    return item_id
                continue   # 防御判定已掷骰：本阶段不再叠加基础分支
            p = fuse_p_live(gun, ai)
            if remaining_slots >= 2 and 0.2 <= p <= 0.8:
                if _draw(0.7):
                    return item_id
        elif item_id == "cigarette":
            return item_id  # 硬校验已排除满血；掉血就抽
        elif item_id == "handsaw":
            if ai.known_shells.get(0) is True:
                if _draw(1.0 - 0.6 * ai.R):
                    return item_id
        elif item_id == "handcuff":
            info_advantage = len(ai.known_shells) > 0
            finisher = (opp.charges or 1) <= 1
            # L2 防御手铐（Phase 4）：对手威胁高——锁住其下回合阻断确定性连招
            defensive = compute_threat(ai.opp_model, opp, ai.charges) >= 0.6
            if finisher or info_advantage or defensive:
                if _draw(0.4 + 0.6 * ai.C):
                    return item_id
    return None
