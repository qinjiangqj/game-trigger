"""DoN 道具与信息公平测试（Phase 3）。

覆盖：反转器/电话/过期药/肾上腺素的效果原语与状态机、
过期药致死、肾上腺素偷取链、启发式人格调制、
get_state(viewer) 私有情报过滤（人机信息公平）。
"""

from __future__ import annotations

import random
import unittest

from engine.decision import next_item_action
from engine.game import GameSession, simulate_match
from engine.items import (check_usable, pick_adrenaline_steal, resolve_item)
from engine.models import AIPlayer, Shotgun


def _ai(name: str = "T", R: float = 0.2, S: float = 0.1, C: float = 0.5,
        L: float = 0.0, human: bool = False, charges: int = 3) -> AIPlayer:
    return AIPlayer(name, "测试", R, S, C, L, is_human=human, max_charges=charges)


def _shotgun(chamber: list[bool]) -> Shotgun:
    sg = Shotgun(rng=random.Random(0))
    sg.chamber = list(chamber)
    sg.total_slots = len(chamber)
    sg.live_bullets = sum(chamber)
    sg.blank_bullets = sg.total_slots - sg.live_bullets
    sg.pointer = 0
    return sg


class TestInverter(unittest.TestCase):
    def test_invert_flips_shell_and_counts(self):
        sg = _shotgun([True, False])
        user, opp = _ai(), _ai()
        new_live = sg.invert()
        self.assertFalse(new_live)
        self.assertEqual(sg.live_bullets, 0)
        self.assertEqual(sg.blank_bullets, 2)

    def test_resolve_updates_both_peepers_knowledge(self):
        sg = _shotgun([True, False])
        user, opp = _ai("A"), _ai("B")
        user.known_shells[0] = True    # 自己偷看过
        opp.known_shells[0] = True     # 对方也偷看过
        user.items = ["inverter"]
        out = resolve_item("inverter", sg, user, opp, rng=random.Random(1))
        self.assertFalse(out["inverted_live"])
        self.assertEqual(user.known_shells[0], False)
        self.assertEqual(opp.known_shells[0], False)   # 偷看过者同步翻转

    def test_check_usable_blocks_empty_gun(self):
        sg = _shotgun([False])
        sg.pointer = 1
        user, opp = _ai(), _ai()
        user.items = ["inverter"]
        self.assertEqual(check_usable("inverter", user, sg, opp), "弹仓已空")


class TestBurnerPhone(unittest.TestCase):
    def test_reveals_unknown_future_shell(self):
        sg = _shotgun([True, False, True, False])
        user, opp = _ai(), _ai()
        user.items = ["burner_phone"]
        rng = random.Random(3)
        out = resolve_item("burner_phone", sg, user, opp, rng=rng)
        offset, is_live = out["phone_offset"], out["phone_live"]
        self.assertGreaterEqual(offset, 1)
        self.assertNotIn(0, user.known_shells)              # 不泄露当前弹
        self.assertEqual(user.known_shells[offset], is_live)
        self.assertEqual(sg.chamber[offset], is_live)       # 情报真实

    def test_blocked_when_no_unknown_future(self):
        sg = _shotgun([True, False])
        user, opp = _ai(), _ai()
        user.items = ["burner_phone"]
        user.known_shells = {1: False}    # 唯一未来弹已知
        self.assertEqual(check_usable("burner_phone", user, sg, opp),
                         "没有可查询的未来弹")


class TestExpiredMedicine(unittest.TestCase):
    def test_heal_branch(self):
        sg = _shotgun([True, False])
        user, opp = _ai(charges=3), _ai()
        user.charges = 1
        user.items = ["expired_medicine"]
        # Random(1) 首个 random()≈0.134 < 0.5 → 药效生效
        out = resolve_item("expired_medicine", sg, user, opp,
                           rng=random.Random(1))
        self.assertTrue(out["healed"])
        self.assertEqual(user.charges, 3)          # 1 + 2，不超上限

    def test_damage_branch_can_kill(self):
        sg = _shotgun([True, False])
        user, opp = _ai(charges=3), _ai()
        user.charges = 1
        user.items = ["expired_medicine"]
        # Random(0) 首个 random()≈0.844 ≥ 0.5 → 药已变质
        out = resolve_item("expired_medicine", sg, user, opp,
                           rng=random.Random(0))
        self.assertFalse(out["healed"])
        self.assertEqual(user.charges, 0)

    def test_blocked_at_full_charges(self):
        sg = _shotgun([True, False])
        user, opp = _ai(charges=3), _ai()
        user.items = ["expired_medicine"]
        self.assertEqual(check_usable("expired_medicine", user, sg, opp),
                         "电荷已满")

    def test_session_ends_on_medicine_death(self):
        g = GameSession(_ai("A"), _ai("B"), mode="buckshot",
                        item_set="full", rng=random.Random(0))
        g.p1.items = ["expired_medicine"]
        g.p1.charges = 1
        g._rng = random.Random(0)   # 首个 random()≥0.5 → 变质 −1 → 致死
        g._use_item(g.p1, "expired_medicine")
        self.assertTrue(g.is_over)
        self.assertEqual(g.winner.name, "B")


class TestAdrenaline(unittest.TestCase):
    def test_steals_and_resolves_stolen_item(self):
        sg = _shotgun([True, False])
        user, opp = _ai("A"), _ai("B")
        user.items = ["adrenaline"]
        opp.items = ["handsaw"]
        out = resolve_item("adrenaline", sg, user, opp, rng=random.Random(1))
        self.assertEqual(out["stolen"], "handsaw")
        self.assertNotIn("handsaw", opp.items)
        self.assertNotIn("adrenaline", user.items)
        self.assertTrue(user.sawed)               # 被偷道具立即生效

    def test_blocked_when_only_adrenaline(self):
        sg = _shotgun([True, False])
        user, opp = _ai(), _ai()
        user.items = ["adrenaline"]
        opp.items = ["adrenaline"]                # 不可偷肾上腺素
        self.assertEqual(check_usable("adrenaline", user, sg, opp),
                         "对方没有可偷取的道具")

    def test_steal_priority_finisher_handcuff(self):
        sg = _shotgun([True, False])
        user, opp = _ai(), _ai(charges=3)
        opp.charges = 1
        opp.items = ["magnifier", "handcuff"]
        self.assertEqual(pick_adrenaline_steal(user, sg, opp), "handcuff")

    def test_steal_priority_handsaw_when_live_known(self):
        sg = _shotgun([True, False])
        user, opp = _ai(), _ai()
        user.known_shells[0] = True
        opp.items = ["handsaw", "magnifier"]
        self.assertEqual(pick_adrenaline_steal(user, sg, opp), "handsaw")

    def test_stolen_beer_empties_magazine(self):
        sg = _shotgun([True])
        user, opp = _ai(), _ai()
        user.items = ["adrenaline"]
        opp.items = ["beer"]
        out = resolve_item("adrenaline", sg, user, opp, rng=random.Random(1))
        self.assertEqual(out["stolen"], "beer")
        self.assertTrue(sg.is_empty)              # 调用方负责重装


class TestDonHeuristics(unittest.TestCase):
    def test_inverter_used_when_live_known(self):
        sg = _shotgun([True, False])
        ai, opp = _ai("A", C=0.9), _ai("B")
        ai.items = ["inverter"]
        ai.known_shells[0] = True
        rng = random.Random(0)
        picks = {next_item_action(ai, sg, opp, rng=rng) for _ in range(30)}
        self.assertIn("inverter", picks)

    def test_medicine_desperate_gambler_vs_cautious(self):
        sg = _shotgun([True, False])
        gambler = _ai("G", R=0.95)
        cautious = _ai("C", R=0.0)
        for p in (gambler, cautious):
            p.items = ["expired_medicine"]
            p.charges = 1
        rng1, rng2 = random.Random(0), random.Random(0)
        g_hits = sum(1 for _ in range(60)
                     if next_item_action(gambler, sg, _ai(), rng=rng1,
                                         attempted=set()) == "expired_medicine")
        c_hits = sum(1 for _ in range(60)
                     if next_item_action(cautious, sg, _ai(), rng=rng2,
                                         attempted=set()) == "expired_medicine")
        self.assertGreater(g_hits, 30)            # 赌徒大概率赌命
        self.assertEqual(c_hits, 0)               # 谨慎人格绝不赌命（p=0）

    def test_phone_gated_by_uncertainty(self):
        sg = _shotgun([True, False, False])
        ai, opp = _ai(), _ai()
        ai.items = ["burner_phone"]
        rng = random.Random(0)
        picks = {next_item_action(ai, sg, opp, rng=rng, attempted=set())
                 for _ in range(30)}
        self.assertIn("burner_phone", picks)
        # 全部未来弹已知 → 不再使用
        ai.known_shells = {1: False, 2: False}
        rng2 = random.Random(0)
        picks2 = {next_item_action(ai, sg, opp, rng=rng2, attempted=set())
                  for _ in range(10)}
        self.assertNotIn("burner_phone", picks2)

    def test_adrenaline_used_when_opp_has_items(self):
        sg = _shotgun([True, False])
        ai, opp = _ai("A", C=0.9), _ai("B")
        ai.items = ["adrenaline"]
        opp.items = ["handsaw"]
        rng = random.Random(0)
        picks = {next_item_action(ai, sg, opp, rng=rng, attempted=set())
                 for _ in range(30)}
        self.assertIn("adrenaline", picks)


class TestViewerFairness(unittest.TestCase):
    """信息公平：私有情报按 viewer 过滤，不再泄露给对手/观众。"""

    def _human_session(self) -> GameSession:
        rng = random.Random(11)
        g = GameSession(_ai("你", human=True), _ai("AI"), mode="buckshot",
                        item_set="full", rng=rng)
        g.p1.items = ["magnifier"]
        return g

    def test_own_peek_visible_to_human(self):
        g = self._human_session()
        g.human_use_item("magnifier")
        state = g.get_state()          # 缺省视角 = 人类玩家
        peeks = [e for e in state["events"] if e["type"] == "peek"]
        self.assertTrue(peeks)
        self.assertNotIn("masked", peeks[-1])
        self.assertIsNotNone(peeks[-1]["is_live"])

    def test_ai_peek_masked_for_human(self):
        g = self._human_session()
        g.current, g.opponent = g.p2, g.p1          # 轮到 AI
        g.p2.items = ["magnifier"]
        g._use_item(g.p2, "magnifier")
        state = g.get_state()
        peeks = [e for e in state["events"] if e["type"] == "peek"]
        self.assertTrue(peeks)
        self.assertTrue(peeks[-1].get("masked"))
        self.assertIsNone(peeks[-1]["is_live"])     # 弹型结果不泄露
        self.assertIn("不可见", peeks[-1]["message"])

    def test_ai_peek_visible_as_ai_viewer(self):
        g = self._human_session()
        g.current, g.opponent = g.p2, g.p1
        g.p2.items = ["magnifier"]
        g._use_item(g.p2, "magnifier")
        state = g.get_state(viewer="AI")
        peeks = [e for e in state["events"] if e["type"] == "peek"]
        self.assertFalse(peeks[-1].get("masked"))
        self.assertIsNotNone(peeks[-1]["is_live"])

    def test_spectator_view_masks_all_peeks(self):
        rng = random.Random(5)
        g = GameSession(_ai("A"), _ai("B"), mode="buckshot", item_set="full",
                        rng=rng)
        g.p1.items = ["magnifier"]
        g._use_item(g.p1, "magnifier")
        state = g.get_state(viewer=None)
        peeks = [e for e in state["events"] if e["type"] == "peek"]
        self.assertTrue(peeks[-1].get("masked"))

    def test_opponent_known_shells_hidden(self):
        g = self._human_session()
        g.p1.known_shells = {0: True}
        g.p2.known_shells = {0: False}
        state = g.get_state()          # 人类视角
        self.assertEqual(state["p1"]["known_shells"], {0: True})
        self.assertEqual(state["p2"]["known_shells"], {})   # 对手私有信息隐藏


class TestFullSetSimulation(unittest.TestCase):
    def test_simulate_match_full_set(self):
        rng = random.Random(20260817)
        tpl = [
            ("Claude", 0.16, 0.65, 0.75, 0.02),
            ("DeepSeek", 0.32, 0.15, 0.20, 0.14),
        ]
        wins = {"Claude": 0, "DeepSeek": 0}
        for _ in range(200):
            a = AIPlayer("Claude", "谨慎稳定", 0.16, 0.65, 0.75, 0.02,
                         max_charges=3)
            b = AIPlayer("DeepSeek", "赌徒狂人", 0.32, 0.15, 0.20, 0.14,
                         max_charges=3)
            winner = simulate_match(a, b, mode="buckshot", item_set="full",
                                    rng=rng)
            wins[winner.name] += 1
        self.assertEqual(sum(wins.values()), 200)
        self.assertGreater(wins["Claude"], 0)
        self.assertGreater(wins["DeepSeek"], 0)

    def test_reproducible_with_same_seed(self):
        def _run(seed: int) -> str:
            rng = random.Random(seed)
            a = AIPlayer("A", "x", 0.2, 0.3, 0.5, 0.05, max_charges=3)
            b = AIPlayer("B", "y", 0.25, 0.2, 0.4, 0.1, max_charges=3)
            return simulate_match(a, b, mode="buckshot", item_set="full",
                                  rng=rng).name
        self.assertEqual(_run(7), _run(7))


if __name__ == "__main__":
    unittest.main()
