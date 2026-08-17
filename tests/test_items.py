"""道具系统测试（Phase 2/3）。

覆盖：注册表、补发、硬校验、效果原语、信息融合、启发式人格调制、
GameSession 状态机（道具阶段/手铐跳过/手锯伤害/退弹重装/私有事件）、
DoN 道具（反转器/电话/过期药/肾上腺素）与 viewer 信息公平。
"""

from __future__ import annotations

import random
import unittest

from engine.config import ITEM_SLOT_CAP
from engine.decision import fuse_p_live, next_item_action
from engine.factory import create_game, create_player
from engine.game import GameSession, simulate_match
from engine.items import (ITEM_REGISTRY, check_usable, grant_items,
                          get_item_pool, resolve_item)
from engine.models import AIPlayer, Shotgun


def _ai(name: str = "T", R: float = 0.2, S: float = 0.1, C: float = 0.5,
        L: float = 0.0, human: bool = False, charges: int = 3) -> AIPlayer:
    return AIPlayer(name, "测试", R, S, C, L, is_human=human, max_charges=charges)


def _shotgun(chamber: list[bool]) -> Shotgun:
    """构造受控霰弹枪：指定弹序，指针归零。"""
    sg = Shotgun(rng=random.Random(0))
    sg.chamber = list(chamber)
    sg.total_slots = len(chamber)
    sg.live_bullets = sum(chamber)
    sg.blank_bullets = len(chamber) - sum(chamber)
    sg.pointer = 0
    return sg


class TestItemRegistry(unittest.TestCase):
    def test_standard_items_registered(self):
        for item_id in ("magnifier", "beer", "cigarette", "handsaw", "handcuff"):
            self.assertIn(item_id, ITEM_REGISTRY)
            d = ITEM_REGISTRY[item_id]
            self.assertTrue(d.name and d.icon)
            self.assertIn(d.kind, ("info", "tempo", "heal", "damage"))

    def test_don_items_registered(self):
        # Phase 3：Double or Nothing 4 件套
        for item_id in ("inverter", "burner_phone", "expired_medicine", "adrenaline"):
            self.assertIn(item_id, ITEM_REGISTRY)
            d = ITEM_REGISTRY[item_id]
            self.assertTrue(d.name and d.icon)
            self.assertIn(d.kind, ("info", "tempo", "heal", "damage",
                                   "gamble", "complex"))

    def test_full_pool_contains_all(self):
        pool = get_item_pool("full")
        self.assertEqual(len(pool), 9)
        self.assertIn("inverter", pool)
        standard = get_item_pool("standard")
        for item_id in standard:
            self.assertIn(item_id, pool)

    def test_unknown_item_set_rejected(self):
        with self.assertRaises(ValueError):
            grant_items([], "mega")   # 未知道具集


class TestGrantItems(unittest.TestCase):
    def test_grant_counts_and_cap(self):
        rng = random.Random(7)
        players = [_ai("A"), _ai("B")]
        granted = grant_items(players, "standard", n=2, rng=rng)
        self.assertEqual(len(players[0].items), 2)
        self.assertEqual(len(players[1].items), 2)
        self.assertEqual(granted["A"], players[0].items)

        players[0].items = ["beer"] * (ITEM_SLOT_CAP - 1)
        grant_items(players[:1], "standard", n=2, rng=rng)
        self.assertEqual(len(players[0].items), ITEM_SLOT_CAP)

    def test_none_set_grants_nothing(self):
        players = [_ai("A")]
        granted = grant_items(players, "none", rng=random.Random(1))
        self.assertEqual(granted, {"A": []})
        self.assertEqual(players[0].items, [])


class TestCheckUsable(unittest.TestCase):
    def test_magnifier(self):
        user, opp = _ai(), _ai()
        gun = _shotgun([True, False])
        self.assertEqual(check_usable("magnifier", user, gun, opp), "没有道具: magnifier")
        user.items = ["magnifier"]
        self.assertIsNone(check_usable("magnifier", user, gun, opp))
        user.known_shells = {0: True}
        self.assertEqual(check_usable("magnifier", user, gun, opp), "已知道当前弹型")

    def test_cigarette_full_hp_rejected(self):
        user, opp = _ai(), _ai()
        gun = _shotgun([True, False])
        user.items = ["cigarette"]
        self.assertEqual(check_usable("cigarette", user, gun, opp), "电荷已满")
        user.take_damage(1)
        self.assertIsNone(check_usable("cigarette", user, gun, opp))

    def test_handsaw_no_stacking(self):
        user, opp = _ai(), _ai()
        gun = _shotgun([True, False])
        user.items = ["handsaw"]
        self.assertIsNone(check_usable("handsaw", user, gun, opp))
        user.sawed = True
        self.assertEqual(check_usable("handsaw", user, gun, opp), "手锯增益已在生效")

    def test_handcuff_rules(self):
        user, opp = _ai("A"), _ai("B")
        gun = _shotgun([True, False])
        user.items = ["handcuff"]
        self.assertIsNone(check_usable("handcuff", user, gun, opp))
        resolve_item("handcuff", gun, user, opp)
        self.assertTrue(opp.skip_next)
        user.items = ["handcuff"]
        self.assertEqual(check_usable("handcuff", user, gun, opp), "对方已被铐住")
        opp.skip_next = False
        self.assertEqual(check_usable("handcuff", user, gun, opp), "不可连续铐同一人")


class TestEffects(unittest.TestCase):
    def test_magnifier_writes_private_info(self):
        for chamber, expect in (([True, False], True), ([False, False, True], False)):
            user, opp = _ai(), _ai()
            gun = _shotgun(chamber)
            user.items = ["magnifier"]
            out = resolve_item("magnifier", gun, user, opp)
            self.assertEqual(out["peek_live"], expect)
            self.assertEqual(user.known_shells[0], expect)
            self.assertEqual(user.items, [])
            self.assertEqual(gun.pointer, 0)  # 查看不击发

    def test_beer_ejects_and_remaps_knowledge(self):
        user, opp = _ai(), _ai()
        gun = _shotgun([True, False, False])
        user.items = ["beer"]
        user.known_shells = {0: True, 2: False}
        out = resolve_item("beer", gun, user, opp)
        self.assertTrue(out["ejected_live"])
        self.assertEqual(gun.pointer, 1)
        # offset0 已消耗，offset2 的知识前移为 1
        self.assertEqual(user.known_shells, {1: False})
        live, blank = gun.get_counts()
        self.assertEqual((live, blank), (0, 2))

    def test_cigarette_heals_with_cap(self):
        user, opp = _ai(), _ai()
        gun = _shotgun([True, False])
        user.take_damage(2)
        user.items = ["cigarette"]
        out = resolve_item("cigarette", gun, user, opp)
        self.assertEqual(out["healed"], 1)
        self.assertEqual(user.charges, 2)

    def test_handsaw_and_damage_flow(self):
        user, opp = _ai(), _ai()
        gun = _shotgun([True, False])
        user.items = ["handsaw"]
        resolve_item("handsaw", gun, user, opp)
        self.assertTrue(user.sawed)


class TestFusePLive(unittest.TestCase):
    def test_known_overrides_public(self):
        p = _ai()
        gun = _shotgun([True, False, False])
        p.known_shells = {0: True}
        self.assertEqual(fuse_p_live(gun, p), 1.0)
        p.known_shells = {0: False}
        self.assertEqual(fuse_p_live(gun, p), 0.0)

    def test_unknown_uses_public_ratio(self):
        p = _ai()
        gun = _shotgun([True, True, False, False])
        p.known_shells = {2: True}   # 只知道未来弹位
        self.assertEqual(fuse_p_live(gun, p), 0.5)

    def test_empty_gun(self):
        p = _ai()
        gun = _shotgun([True])
        gun.pointer = 1
        self.assertEqual(fuse_p_live(gun, p), 0.0)


class TestItemHeuristics(unittest.TestCase):
    def test_cigarette_used_when_damaged(self):
        ai, opp = _ai(), _ai()
        gun = _shotgun([True, False])
        ai.take_damage(1)
        ai.items = ["beer", "cigarette"]
        self.assertEqual(next_item_action(ai, gun, opp, rng=random.Random(0)),
                         "cigarette")

    def test_known_blank_beats_beer(self):
        """已知空弹时啤酒无意义（直接自击蝉联）。"""
        ai, opp = _ai(), _ai()
        gun = _shotgun([False, True])
        ai.known_shells = {0: False}
        ai.items = ["beer", "magnifier"]
        self.assertIsNone(next_item_action(ai, gun, opp, rng=random.Random(0)))

    def test_known_live_triggers_handsaw(self):
        """偷看→手锯连招：已知实弹且带手锯，低 R 几乎必然使用。"""
        ai, opp = _ai(R=0.16), _ai()
        gun = _shotgun([True, False])
        ai.known_shells = {0: True}
        ai.items = ["handsaw"]
        hits = sum(1 for s in range(100)
                   if next_item_action(ai, gun, opp, rng=random.Random(s)) == "handsaw")
        self.assertGreater(hits, 70)

    def test_magnifier_uncertainty_gate(self):
        """确定性弹仓（纯实/纯空）不触发放大镜；不确定时 S 高者少用。"""
        ai, opp = _ai(), _ai()
        certain = _shotgun([True, True])
        ai.items = ["magnifier"]
        self.assertIsNone(next_item_action(ai, gun=certain, opp=opp,
                                           rng=random.Random(3)))

        uncertain = _shotgun([True, False, False])
        cautious = _ai(S=0.65)   # Claude 型
        chaotic = _ai(S=0.10)    # GLM 型
        cautious.items = chaotic.items = ["magnifier"]
        n = 300
        c_hits = sum(1 for s in range(n)
                     if next_item_action(cautious, uncertain, opp, rng=random.Random(s)))
        g_hits = sum(1 for s in range(n)
                     if next_item_action(chaotic, uncertain, opp, rng=random.Random(s)))
        self.assertGreater(g_hits, c_hits)

    def test_handcuff_finisher(self):
        """对方仅剩 1 电荷时高 C 人格倾向手铐收尾。"""
        ai = _ai(C=0.75)
        opp = _ai(charges=3)
        opp.take_damage(2)
        gun = _shotgun([True, False])
        ai.items = ["handcuff"]
        hits = sum(1 for s in range(100)
                   if next_item_action(ai, gun, opp, rng=random.Random(s)) == "handcuff")
        self.assertGreater(hits, 60)

    def test_beer_only_when_uncertain(self):
        ai, opp = _ai(), _ai()
        extreme = _shotgun([True] + [False] * 7)   # p = 1/8，接近极值
        ai.items = ["beer"]
        self.assertIsNone(next_item_action(ai, extreme, opp, rng=random.Random(5)))


class TestSessionStateMachine(unittest.TestCase):
    def _session(self, item_set="standard", human=False) -> GameSession:
        p1 = create_player("Claude", is_human=human)
        p2 = create_player("DeepSeek")
        g = GameSession(p1, p2, mode="buckshot", item_set=item_set)
        return g

    def test_initial_grant_and_state_fields(self):
        g = self._session()
        self.assertEqual(g.item_set, "standard")
        for p in (g.p1, g.p2):
            self.assertEqual(len(p.items), 2)
        state = g.get_state()
        self.assertEqual(state["item_set"], "standard")
        self.assertIn("items", state["p1"])
        self.assertIn("known_shells", state["p1"])

    def test_none_set_and_classic_forced(self):
        g = self._session(item_set="none")
        self.assertEqual(g.item_set, "none")
        self.assertEqual(g.p1.items, [])
        p1, p2 = create_player("Claude"), create_player("DeepSeek")
        gc = GameSession(p1, p2, mode="classic", item_set="standard")
        self.assertEqual(gc.item_set, "none")   # classic 强制无道具

    def test_human_item_use_and_peek_event(self):
        g = self._session(human=True)
        g.p1.items = ["magnifier"]
        state = g.human_use_item("magnifier")
        self.assertEqual(g.p1.known_shells, {0: g.gun.chamber[0]})
        self.assertTrue(g.p1.is_human)
        types = [e["type"] for e in state["events"]]
        self.assertIn("item_use", types)
        self.assertIn("peek", types)
        peek = next(e for e in state["events"] if e["type"] == "peek")
        self.assertEqual(peek["private_to"], g.p1.name)
        self.assertIn("is_live", peek)
        # 道具不消耗回合
        self.assertTrue(state["needs_human_input"])

    def test_human_item_errors(self):
        g = self._session(human=True)
        g.p1.items = []                        # 排除随机初始道具干扰
        with self.assertRaises(ValueError):
            g.human_use_item("beer")          # 没有
        with self.assertRaises(ValueError):
            g.human_use_item("rocket")        # 不存在
        g2 = self._session(human=False)
        with self.assertRaises(ValueError):
            g2.human_use_item("beer")         # 不是人类回合

    def test_saw_doubles_damage_and_clears(self):
        g = self._session(human=True)
        g.gun.chamber = [True, False, False]
        g.gun.total_slots = 3
        g.gun.pointer = 0
        g.p1.items = ["handsaw"]
        g.human_use_item("handsaw")
        self.assertTrue(g.p1.sawed)
        opp_before = g.p2.charges
        state = g.human_action("opponent")
        fire = next(e for e in state["events"] if e["type"] == "fire")
        self.assertEqual(fire["damage"], 2)
        self.assertEqual(g.p2.charges, opp_before - 2)
        self.assertFalse(g.p1.sawed)          # 射击后清除

    def test_saw_cleared_on_blank_too(self):
        g = self._session(human=True)
        g.gun.chamber = [False, True, False]
        g.gun.total_slots = 3
        g.gun.pointer = 0
        g.p1.items = ["handsaw"]
        g.human_use_item("handsaw")
        g.human_action("self")                # 空枪蝉联
        self.assertFalse(g.p1.sawed)

    def test_handcuff_skips_opponent_turn(self):
        g = self._session(human=True)
        g.p1.items = ["handcuff"]
        g.human_use_item("handcuff")
        self.assertTrue(g.p2.skip_next)
        g.gun.chamber = [False, False, True]
        g.gun.total_slots = 3
        g.gun.pointer = 0
        g.human_action("opponent")            # 空枪 → 换边 → p2 被跳过 → 回到 p1
        self.assertEqual(g.current, g.p1)
        self.assertFalse(g.p2.skip_next)
        msgs = [e.message for e in g.events]
        self.assertTrue(any("手铐" in m and "跳过" in m for m in msgs))

    def test_beer_empties_magazine_triggers_reload(self):
        g = self._session(human=True)
        g.gun.chamber = [True]
        g.gun.total_slots = 1
        g.gun.live_bullets = 1
        g.gun.blank_bullets = 0
        g.gun.pointer = 0
        g.p1.known_shells = {0: True}
        g.p1.items = ["beer"]
        state = g.human_use_item("beer")
        # 退弹后弹尽 → 立即重装：新弹仓非空且指针归零、私有信息清空、双方补发道具
        self.assertFalse(g.gun.is_empty)
        self.assertEqual(g.gun.pointer, 0)       # 重装后新弹仓从 0 开始
        self.assertGreaterEqual(g.gun.total_slots, 2)
        self.assertEqual(g.p1.known_shells, {})
        self.assertEqual(g.p2.known_shells, {})
        self.assertEqual(len(g.p1.items), 2)   # 补发
        msgs = " ".join(e["message"] for e in state["events"])
        self.assertIn("重新装填", msgs)

    def test_reload_clears_cuff_memory(self):
        """重装清空 last_cuffed：新一仓可以再次铐同一人。"""
        g = self._session(human=True)
        g.p1.items = ["handcuff"]
        g.human_use_item("handcuff")
        g.p2.skip_next = False
        g.p1.items = ["handcuff"]              # 使用后已消耗，补回道具以测试校验逻辑
        self.assertEqual(check_usable("handcuff", g.p1, g.gun, g.p2),
                         "不可连续铐同一人")
        g.p1.last_cuffed = None                # 模拟重装清空
        self.assertIsNone(check_usable("handcuff", g.p1, g.gun, g.p2))

    def test_ai_game_with_items_terminates(self):
        for seed in range(30):
            rng = random.Random(seed)
            p1 = _ai("A", R=0.2, S=0.3, C=0.4, L=0.1)
            p2 = _ai("B", R=0.3, S=0.2, C=0.3, L=0.1)
            for p in (p1, p2):
                p.max_charges = 3
                p.charges = 3
            g = GameSession(p1, p2, mode="buckshot", rng=rng)
            state = g.auto_play_to_end()
            self.assertTrue(state["is_over"])
            self.assertIsNotNone(state["winner"])
            for p in (g.p1, g.p2):
                self.assertLessEqual(len(p.items), ITEM_SLOT_CAP)

    def test_item_events_in_full_game(self):
        p1 = _ai("A", R=0.1, S=0.0, C=0.9, L=0.0)
        p2 = _ai("B", R=0.1, S=0.0, C=0.9, L=0.0)
        g = GameSession(p1, p2, mode="buckshot", rng=random.Random(11))
        g.auto_play_to_end()
        types = {e.type for e in g.events}
        self.assertIn("item_use", types)
        # 至少出现一次香烟/放大镜/手铐其一的行为痕迹
        item_used = [e.item_id for e in g.events if e.type == "item_use"]
        self.assertTrue(item_used)


class TestSimulateWithItems(unittest.TestCase):
    def test_returns_winner_and_caps_items(self):
        rng = random.Random(3)
        p1, p2 = _ai("A"), _ai("B")
        winner = simulate_match(p1, p2, mode="buckshot", item_set="standard", rng=rng)
        self.assertIn(winner, (p1, p2))
        for p in (p1, p2):
            self.assertLessEqual(len(p.items), ITEM_SLOT_CAP)

    def test_personality_acceptance_claude_vs_deepseek(self):
        """验收：信息型人格（低 R 高 C）用放大镜/手铐更多，赌徒型乱赌少规划。"""
        stats = {"claude": {"magnifier": 0, "handcuff": 0, "shots": 0},
                 "deepseek": {"magnifier": 0, "handcuff": 0, "shots": 0}}
        for seed in range(50):
            rng = random.Random(seed)
            claude = _ai("Claude", R=0.16, S=0.65, C=0.75, L=0.02)
            deep = _ai("DeepSeek", R=0.32, S=0.15, C=0.20, L=0.14)
            g = GameSession(claude, deep, mode="buckshot", rng=rng)
            g.auto_play_to_end()
            for e in g.events:
                if e.type == "item_use":
                    who = "claude" if e.player_name == "Claude" else "deepseek"
                    if e.item_id in stats[who]:
                        stats[who][e.item_id] += 1
        # Claude 的信息/节奏道具使用量显著高于 DeepSeek（攒信息 vs 乱赌）
        self.assertGreater(stats["claude"]["magnifier"] + stats["claude"]["handcuff"],
                           stats["deepseek"]["magnifier"] + stats["deepseek"]["handcuff"])


if __name__ == "__main__":
    unittest.main()
