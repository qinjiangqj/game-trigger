"""对手建模测试（Phase 4 L2+）。

覆盖：信息层信念（放大镜/反转器/电话到期）、行为层贝叶斯反推
（高p自击空/低p击敌/手锯）、指针推进与重装重置、威胁评估、
效用内核威胁偏置、防御性啤酒/手铐、人格保持（C 调制）、
信息公平（模型不进公开状态、breakdown 无弹型泄露）、模拟一致性。
"""

from __future__ import annotations

import random
import unittest

from engine.decision import make_utility_decision, next_item_action
from engine.factory import create_player
from engine.game import GameSession, simulate_match
from engine.items import resolve_item
from engine.models import AIPlayer, Shotgun
from engine.theory import OpponentModel, compute_threat


def _ai(name: str = "T", R: float = 0.2, S: float = 0.1, C: float = 0.5,
        L: float = 0.0, human: bool = False, charges: int = 3) -> AIPlayer:
    return AIPlayer(name, "测试", R, S, C, L, is_human=human, max_charges=charges)


def _shotgun(chamber: list[bool]) -> Shotgun:
    sg = Shotgun(rng=random.Random(0))
    sg.chamber = list(chamber)
    sg.total_slots = len(chamber)
    sg.live_bullets = sum(chamber)
    sg.blank_bullets = len(chamber) - sum(chamber)
    sg.pointer = 0
    return sg


class TestInfoLayer(unittest.TestCase):
    def test_magnifier_observation(self):
        m = OpponentModel()
        m.observe_item("magnifier", public_p_live=0.6, phone_pool=0)
        self.assertEqual(m.peek_current, 1.0)
        self.assertEqual(m.peek_live, 0.6)
        self.assertEqual(m.info_current(), 1.0)
        self.assertAlmostEqual(m.p_knows_live(), 0.6)

    def test_handsaw_observation_infers_live(self):
        m = OpponentModel()
        m.observe_item("handsaw", 0.5, 0)
        self.assertGreaterEqual(m.p_knows_live(), 0.9)

    def test_phone_expiry_progression(self):
        m = OpponentModel()
        m.observe_item("burner_phone", 0.5, phone_pool=4)
        self.assertTrue(m.has_phone)
        self.assertAlmostEqual(m.phone_expired, 0.0)
        for _ in range(2):
            m.on_advance()
        self.assertAlmostEqual(m.phone_expired, 0.5)
        for _ in range(2):
            m.on_advance()
        self.assertAlmostEqual(m.phone_expired, 1.0)
        self.assertAlmostEqual(m.info_current(), 1.0)

    def test_advance_consumes_peek(self):
        m = OpponentModel()
        m.observe_item("magnifier", 0.6, 0)
        self.assertEqual(m.info_current(), 1.0)
        m.on_advance()
        self.assertEqual(m.peek_current, 0.0)
        self.assertEqual(m.info_current(), 0.0)

    def test_behavior_evidence_decays(self):
        m = OpponentModel()
        m.behavior_info = 0.7
        m.on_advance()
        self.assertAlmostEqual(m.behavior_info, 0.42)


class TestBehaviorInference(unittest.TestCase):
    def test_high_p_self_blank_infers_blank_info(self):
        m = OpponentModel()
        m.observe_shot("self", was_live=False, public_p_live_before=0.75)
        self.assertGreaterEqual(m.behavior_info, 0.7)
        self.assertLessEqual(m.peek_live, 0.15)
        self.assertGreaterEqual(m.p_knows_blank(), 0.7 * 0.85)

    def test_low_p_attack_infers_live_info(self):
        m = OpponentModel()
        self.assertAlmostEqual(m.peek_live, 0.5)
        m.observe_shot("opponent", was_live=True, public_p_live_before=0.25)
        self.assertGreaterEqual(m.behavior_info, 0.4)
        self.assertAlmostEqual(m.peek_live, 0.75)

    def test_peeked_opponent_behavior_not_reread(self):
        # 已用放大镜的对手行为不再新增证据
        m = OpponentModel()
        m.observe_item("magnifier", 0.5, 0)
        before = m.behavior_info
        m.observe_shot("self", False, 0.8)
        self.assertEqual(m.behavior_info, before)

    def test_neutral_actions_no_evidence(self):
        m = OpponentModel()
        m.observe_shot("self", False, public_p_live_before=0.4)
        m.observe_shot("opponent", True, public_p_live_before=0.5)
        self.assertEqual(m.behavior_info, 0.0)


class TestThreat(unittest.TestCase):
    def test_no_info_low_threat(self):
        m = OpponentModel()
        opp = _ai("Opp")
        opp.items = ["handsaw", "handcuff"]
        self.assertLess(compute_threat(m, opp, 3), 0.15)

    def test_live_info_and_saw_high_threat(self):
        m = OpponentModel()
        m.observe_item("magnifier", 0.9, 0)
        opp = _ai("Opp")
        opp.sawed = True
        self.assertGreaterEqual(compute_threat(m, opp, 3), 0.5)

    def test_finisher_bonus_when_low_hp(self):
        m = OpponentModel()
        m.observe_item("magnifier", 0.9, 0)
        opp = _ai("Opp")
        opp.sawed = True
        self.assertGreater(compute_threat(m, opp, 1),
                           compute_threat(m, opp, 3))


class TestUtilityThreatBias(unittest.TestCase):
    def test_threat_shifts_toward_attack(self):
        # 构造接近中立的局面：高威胁应把冷静者推向击敌
        rng = random.Random(42)
        calm = _ai("calm", C=0.9, L=0.0)
        calm.M = 0.0
        rng.random = lambda: 0.99   # 抑制惯性与噪声路径（L=0 时噪声为 0）
        _, base = make_utility_decision(calm, 0.5, 3, 3, rng=rng)
        diff_base = base.raw_diff
        _, threatened = make_utility_decision(calm, 0.5, 3, 3, rng=rng,
                                              opp_threat=0.9)
        self.assertAlmostEqual(threatened.raw_diff - diff_base,
                               0.9 * 0.9 * 0.4, places=6)

    def test_low_c_personality_ignores_threat(self):
        # 低 C 人格几乎不受威胁影响——人格保持
        rng = random.Random(7)
        hot = _ai("hot", C=0.05, L=0.0)
        _, base = make_utility_decision(hot, 0.5, 3, 3, rng=rng)
        _, threatened = make_utility_decision(hot, 0.5, 3, 3, rng=rng,
                                              opp_threat=1.0)
        self.assertAlmostEqual(threatened.raw_diff - base.raw_diff,
                               0.05 * 0.4, places=6)

    def test_breakdown_carries_threat_fields(self):
        rng = random.Random(1)
        ai = _ai("t")
        _, bd = make_utility_decision(ai, 0.5, 3, 3, rng=rng, opp_threat=0.7)
        d = bd.to_dict()
        self.assertEqual(d["opp_threat"], 0.7)
        self.assertIn("threat_bias", d)


class TestDefensiveItems(unittest.TestCase):
    def test_defensive_beer_destroys_opp_info(self):
        # 对手（模型视角）握实弹情报且有锯 → 高 C 者高频退弹
        uses = 0
        for seed in range(300):
            ai = _ai("A", C=0.9)
            ai.items = ["beer"]
            opp = _ai("B")
            opp.sawed = True
            ai.opp_model.observe_item("magnifier", 0.9, 0)
            gun = _shotgun([True, False, True])
            rng = random.Random(seed)
            if next_item_action(ai, gun, opp, rng=rng) == "beer":
                uses += 1
        self.assertGreater(uses / 300, 0.7)

    def test_beer_not_wasted_when_self_knows(self):
        # 自己已知道当前弹型：不退（沿用既有规则）
        ai = _ai("A", C=0.9)
        ai.items = ["beer"]
        ai.known_shells = {0: False}
        ai.opp_model.observe_item("magnifier", 0.9, 0)
        opp = _ai("B")
        opp.sawed = True
        gun = _shotgun([False, True, False])
        self.assertIsNone(next_item_action(ai, gun, opp, rng=random.Random(1)))

    def test_low_c_rarely_defensive_beer(self):
        uses = 0
        for seed in range(300):
            ai = _ai("A", C=0.1)
            ai.items = ["beer"]
            opp = _ai("B")
            opp.sawed = True
            ai.opp_model.observe_item("magnifier", 0.9, 0)
            gun = _shotgun([True, False, True])   # p=2/3 ∈ [0.2,0.8]
            rng = random.Random(seed)
            if next_item_action(ai, gun, opp, rng=rng) == "beer":
                uses += 1
        # 防御分支独占掷骰：低 C 只剩 0.5+0.4×0.1≈0.54，显著低于高 C 的 0.86
        self.assertLess(uses / 300, 0.65)

    def test_defensive_handcuff_on_high_threat(self):
        uses = 0
        for seed in range(300):
            ai = _ai("A", C=0.9)
            ai.items = ["handcuff"]
            opp = _ai("B")
            opp.sawed = True
            ai.opp_model.observe_item("magnifier", 0.95, 0)
            gun = _shotgun([True, False])
            rng = random.Random(seed)
            if next_item_action(ai, gun, opp, rng=rng) == "handcuff":
                uses += 1
        self.assertGreater(uses / 300, 0.8)


class TestSessionIntegration(unittest.TestCase):
    def test_reset_on_prepare_and_reload(self):
        g = GameSession(_ai("A"), _ai("B"), mode="buckshot", item_set="full",
                        rng=random.Random(3))
        g.p2.opp_model.observe_item("magnifier", 0.8, 0)
        g.p1.prepare_for_match("B")
        # prepare 只重置本人模型
        self.assertEqual(g.p1.opp_model.peek_current, 0.0)
        self.assertEqual(g.p2.opp_model.peek_current, 1.0)
        g._check_reload.__self__   # noqa: B018 —— 引用保持
        g.gun.pointer = g.gun.total_slots
        g._check_reload()
        self.assertEqual(g.p2.opp_model.peek_current, 0.0)

    def test_shot_observation_updates_models(self):
        g = GameSession(_ai("A"), _ai("B"), mode="buckshot", item_set="none",
                        rng=random.Random(5))
        # 受控弹仓：当前实弹概率 0.75
        g.gun.chamber = [False, True, True, True]
        g.gun.total_slots = 4
        g.gun.live_bullets = 3
        g.gun.blank_bullets = 1
        g.gun.pointer = 0
        g.current.last_choice = None
        g._execute_shot_buckshot("self")   # 高 p 自击（结果空弹 → 蝉联）
        # B 对 A 的信念：高 p 自击空 → A 握空弹情报
        self.assertGreaterEqual(g.p2.opp_model.behavior_info, 0.7)

    def test_item_use_observed_by_opponent(self):
        g = GameSession(_ai("A"), _ai("B"), mode="buckshot", item_set="full",
                        rng=random.Random(11))
        g.p1.items = ["magnifier"]
        g._use_item(g.p1, "magnifier")
        # B 观察到 A 用放大镜 → B 认为 A 已知当前弹
        self.assertEqual(g.p2.opp_model.peek_current, 1.0)

    def test_get_state_has_no_belief_leak(self):
        g = GameSession(_ai("A"), _ai("B"), mode="buckshot", item_set="full",
                        rng=random.Random(13))
        g.p1.items = ["magnifier"]
        g._use_item(g.p1, "magnifier")
        state = g.get_state(viewer="B")
        s = str(state)
        self.assertNotIn("opp_model", s)
        self.assertNotIn("peek_current", s)

    def test_breakdown_threat_from_public_info_only(self):
        # A 完全无情报时威胁评估仅反映公开信息（对手道具栏/公开状态）
        g = GameSession(_ai("A"), _ai("B"), mode="buckshot", item_set="none",
                        rng=random.Random(17))
        g.p2.sawed = False
        g.p2.items = []
        g.ai_step()
        for e in g.events:
            if e.breakdown is not None:
                self.assertLessEqual(e.breakdown.get("opp_threat", 0), 0.05)

    def test_simulate_match_runs_with_models(self):
        rng = random.Random(20260817)
        p1 = create_player("Claude")
        p2 = create_player("DeepSeek")
        winners = {p1.name: 0, p2.name: 0}
        for _ in range(200):
            w = simulate_match(p1, p2, mode="buckshot", item_set="full",
                               rng=random.Random(rng.random()))
            winners[w.name] += 1
        self.assertEqual(sum(winners.values()), 200)


if __name__ == "__main__":
    unittest.main()
