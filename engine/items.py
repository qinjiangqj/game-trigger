"""道具系统（恶魔轮盘 Phase 2/3）。

三类道具对应三种博弈维度：
  信息类（放大镜/电话）消除不确定性
  节奏类（啤酒/手铐/肾上腺素）争夺行动权
  恢复/伤害类（香烟/过期药/手锯）管理资源与放大收益
  复合类（反转器/肾上腺素）改写博弈结构

本模块只提供注册表与纯效果函数（操作 gun/user/opp 状态对象），
事件发射与校验编排由 GameSession._use_item 完成——保持单向依赖。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import (ITEM_SLOT_CAP, ITEMS_PER_RELOAD, STANDARD_ITEMS,
                     DON_ITEMS, FULL_ITEMS, EXPIRED_MEDICINE_HEAL_CHANCE)
from .models import AIPlayer, Shotgun


@dataclass(frozen=True)
class ItemDef:
    id: str
    name: str
    icon: str
    kind: str          # info / tempo / heal / damage / gamble / complex
    description: str


ITEM_REGISTRY: dict[str, ItemDef] = {
    "magnifier": ItemDef("magnifier", "放大镜", "🔍", "info",
                         "查看当前弹是实是空（仅自己可见）"),
    "beer": ItemDef("beer", "啤酒", "🍺", "tempo",
                    "退掉当前弹，退出的弹型公开"),
    "cigarette": ItemDef("cigarette", "香烟", "🚬", "heal",
                         "回复 1 电荷（不超上限）"),
    "handsaw": ItemDef("handsaw", "手锯", "🪚", "damage",
                       "下次实弹伤害 ×2（状态公开，任意射击后清除）"),
    "handcuff": ItemDef("handcuff", "手铐", "🔗", "tempo",
                        "跳过对方下一回合（不可连续铐同一人）"),
    # Double or Nothing 追加（Phase 3）
    "inverter": ItemDef("inverter", "反转器", "🔄", "complex",
                        "当前弹实↔空互换（结果仅自己可见；偷看过者信息同步翻转）"),
    "burner_phone": ItemDef("burner_phone", "电话", "📱", "info",
                            "随机获知一发未来弹的位置与类型（仅自己可见）"),
    "expired_medicine": ItemDef("expired_medicine", "过期药", "💊", "gamble",
                                "五五开：+2 电荷 或 −1 电荷（电荷归零即出局）"),
    "adrenaline": ItemDef("adrenaline", "肾上腺素", "💉", "complex",
                          "偷取对方一个道具并立即使用（不可偷肾上腺素）"),
}

# 肾上腺素不可偷取的道具
UNSTEALABLE = ("adrenaline",)


def usable_stealable(user: AIPlayer, gun: Shotgun, opp: AIPlayer) -> set[str]:
    """对方道具中可被肾上腺素偷取且当前可用的集合（偷来必须能立即结算）。

    以 user 视角评估对方道具的效果可用性（跳过所有权检查）。
    """
    return {i for i in opp.items
            if i not in UNSTEALABLE
            and _check_effect(i, user, gun, opp) is None}


def get_item_pool(item_set: str) -> tuple[str, ...]:
    if item_set == "none":
        return ()
    if item_set == "standard":
        return tuple(STANDARD_ITEMS)
    if item_set == "full":
        return tuple(FULL_ITEMS)
    raise ValueError(f"Unknown item set: {item_set}")


def grant_items(players: Sequence[AIPlayer], item_set: str,
                n: int = ITEMS_PER_RELOAD,
                rng: Optional[random.Random] = None) -> dict[str, list[str]]:
    """给每位玩家随机补发 n 个道具（上限 ITEM_SLOT_CAP）。返回 {玩家名: 新道具列表}。"""
    _rng = rng if rng is not None else random
    pool = get_item_pool(item_set)
    granted: dict[str, list[str]] = {}
    if not pool:
        return {p.name: [] for p in players}
    for p in players:
        room = ITEM_SLOT_CAP - len(p.items)
        take = max(0, min(n, room))
        new_items = list(_rng.choices(pool, k=take)) if take > 0 else []
        p.items.extend(new_items)
        granted[p.name] = new_items
    return granted


# ==================== 可用性校验 ====================

def unknown_phone_offsets(user: AIPlayer, gun: Shotgun) -> list[int]:
    """电话可查询的未来弹偏移（≥1 且未在私有信息集中的）。"""
    _, remaining_slots = gun.get_remaining()
    return [o for o in range(1, remaining_slots)
            if o not in user.known_shells]


def _check_effect(item_id: str, user: AIPlayer, gun: Shotgun,
                  opp: AIPlayer) -> Optional[str]:
    """效果层校验（不含所有权检查）。check_usable 与肾上腺素偷取共用。"""
    if item_id not in ITEM_REGISTRY:
        return f"未知道具: {item_id}"

    if item_id in ("magnifier", "beer", "inverter", "burner_phone"):
        if gun.is_empty:
            return "弹仓已空"
    if item_id == "magnifier" and 0 in user.known_shells:
        return "已知道当前弹型"
    if item_id == "burner_phone" and not unknown_phone_offsets(user, gun):
        return "没有可查询的未来弹"
    if item_id in ("cigarette", "expired_medicine"):
        if user.charges is None or user.max_charges is None:
            return "本模式无电荷"
        if user.charges >= user.max_charges:
            return "电荷已满"
    if item_id == "handsaw" and user.sawed:
        return "手锯增益已在生效"
    if item_id == "handcuff":
        if opp.skip_next:
            return "对方已被铐住"
        if user.last_cuffed == opp.name:
            return "不可连续铐同一人"
    if item_id == "adrenaline" and not usable_stealable(user, gun, opp):
        return "对方没有可偷取的道具"
    return None


def check_usable(item_id: str, user: AIPlayer, gun: Shotgun,
                 opp: AIPlayer) -> Optional[str]:
    """硬校验：返回 None 表示可用，否则返回拒绝原因。"""
    if item_id not in ITEM_REGISTRY:
        return f"未知道具: {item_id}"
    if item_id not in user.items:
        return f"没有道具: {item_id}"
    return _check_effect(item_id, user, gun, opp)


# ==================== 纯效果函数 ====================

def effect_magnifier(gun: Shotgun, user: AIPlayer) -> bool:
    """写入私有信息集：known_shells[0] = 当前弹型。返回弹型。"""
    is_live = gun.peek()
    user.known_shells[0] = is_live
    return is_live


def effect_beer(gun: Shotgun) -> bool:
    """退掉当前弹（弹型公开）。调用方需为双方执行 advance_known()。"""
    return gun.eject()


def effect_cigarette(user: AIPlayer) -> int:
    return user.heal(1)


def effect_handsaw(user: AIPlayer) -> None:
    user.sawed = True


def effect_handcuff(user: AIPlayer, opp: AIPlayer) -> None:
    opp.skip_next = True
    user.last_cuffed = opp.name


def effect_inverter(gun: Shotgun, user: AIPlayer, opp: AIPlayer) -> bool:
    """反转当前弹。公开实/空计数随之变化（原作规则）；偷看过 offset 0
    的双方私有信息同步翻转。返回反转后的弹型（仅使用者可见）。"""
    new_live = gun.invert()
    for p in (user, opp):
        if 0 in p.known_shells:
            p.known_shells[0] = not p.known_shells[0]
    return new_live


def effect_burner_phone(gun: Shotgun, user: AIPlayer,
                        rng: random.Random) -> tuple[int, bool]:
    """随机查询一发未知未来弹，写入私有信息集。返回 (偏移, 弹型)。"""
    offsets = unknown_phone_offsets(user, gun)
    offset = rng.choice(offsets)
    is_live = gun.peek_at(offset)
    user.known_shells[offset] = is_live
    return offset, is_live


def effect_expired_medicine(user: AIPlayer,
                            rng: random.Random) -> tuple[bool, int]:
    """五五开：+2 电荷 或 −1 电荷。返回 (是否生效, 电荷变化)。"""
    if rng.random() < EXPIRED_MEDICINE_HEAL_CHANCE:
        return True, user.heal(2)
    user.charges = max(0, user.charges - 1)
    return False, -1


def pick_adrenaline_steal(user: AIPlayer, gun: Shotgun,
                          opp: AIPlayer) -> Optional[str]:
    """肾上腺素偷取优先级：按当前局面挑最有价值的可偷道具。"""
    stealable = usable_stealable(user, gun, opp)
    if not stealable:
        return None

    remaining_live, remaining_slots = gun.get_remaining()
    p_live = remaining_live / remaining_slots if remaining_slots else 0.0
    knows_current = 0 in user.known_shells
    known_live = user.known_shells.get(0) is True
    damaged = user.charges is not None and user.charges < user.max_charges

    priority: list[str] = []
    if opp.charges is not None and opp.charges <= 1 and "handcuff" in stealable:
        return "handcuff"                     # 收尾：锁节奏拖一回合
    if "magnifier" in stealable and not knows_current and 0 < p_live < 1:
        priority.append("magnifier")          # 不确定时偷侦察
    if "handsaw" in stealable and (known_live or p_live >= 0.6):
        priority.append("handsaw")            # 高确定性时偷伤害放大
    if ("expired_medicine" in stealable and user.charges is not None
            and user.charges == 1):
        priority.append("expired_medicine")   # 濒死偷药赌命
    if "cigarette" in stealable and damaged:
        priority.append("cigarette")          # 掉血偷烟回稳
    priority += ["magnifier", "handsaw", "handcuff", "cigarette",
                 "burner_phone", "beer", "inverter", "expired_medicine"]
    for item_id in priority:
        if item_id in stealable:
            return item_id
    return None


def _public_p_live(gun: Shotgun) -> float:
    """公开实弹概率（观察者视角，不含任何私有信息）。"""
    live, slots = gun.get_remaining()
    return live / slots if slots else 0.5


def resolve_item(item_id: str, gun: Shotgun, user: AIPlayer,
                 opp: AIPlayer, rng: Optional[random.Random] = None) -> dict:
    """执行道具效果并维护指针相关状态（不发射事件）。GameSession 与轻量模拟共用。

    调用前置条件：check_usable 已通过、道具在 user.items 中。
    啤酒退弹导致的弹尽重装、过期药致死的终局判定由调用方处理。
    道具使用公开：opp 的信念模型同步观察（Phase 4 L2+）。
    """
    _rng = rng if rng is not None else random
    user.items.remove(item_id)
    if item_id == "magnifier":
        out = {"item": item_id, "peek_live": effect_magnifier(gun, user)}
        opp.opp_model.observe_item("magnifier", _public_p_live(gun), 0)
        return out
    if item_id == "beer":
        ejected_live = effect_beer(gun)
        user.advance_known()
        opp.advance_known()
        user.opp_model.on_advance()   # 指针前移：双方模型同步（电话到期推进）
        opp.opp_model.on_advance()
        return {"item": item_id, "ejected_live": ejected_live}
    if item_id == "cigarette":
        return {"item": item_id, "healed": effect_cigarette(user)}
    if item_id == "handsaw":
        effect_handsaw(user)
        opp.opp_model.observe_item("handsaw", _public_p_live(gun), 0)
        return {"item": item_id}
    if item_id == "handcuff":
        effect_handcuff(user, opp)
        return {"item": item_id}
    if item_id == "inverter":
        new_live = effect_inverter(gun, user, opp)
        # 反转后公开配比已变：观察者以新配比重估对手情报为实弹的先验
        opp.opp_model.observe_item("inverter", _public_p_live(gun), 0)
        return {"item": item_id, "inverted_live": new_live}
    if item_id == "burner_phone":
        offset, is_live = effect_burner_phone(gun, user, _rng)
        _, remaining_slots = gun.get_remaining()
        # 观察者不知具体偏移：以可选偏移上限近似到期分布
        opp.opp_model.observe_item("burner_phone", 0.5, max(1, remaining_slots - 1))
        return {"item": item_id, "phone_offset": offset, "phone_live": is_live}
    if item_id == "expired_medicine":
        healed, delta = effect_expired_medicine(user, _rng)
        return {"item": item_id, "healed": healed, "delta": delta}
    if item_id == "adrenaline":
        stolen = pick_adrenaline_steal(user, gun, opp)
        if stolen is None:
            return {"item": item_id, "stolen": None}
        opp.items.remove(stolen)
        user.items.append(stolen)   # 转移道具栏后再结算（复用 resolve_item 前置条件）
        sub = resolve_item(stolen, gun, user, opp, rng=_rng)
        return {"item": item_id, "stolen": stolen, "stolen_result": sub}
    raise ValueError(f"Unhandled item: {item_id}")
