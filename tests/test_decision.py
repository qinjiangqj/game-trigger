"""make_decision 决策引擎单元测试。"""

from __future__ import annotations

import unittest

from engine.decision import make_decision
from engine.models import AIPlayer


def _make_ai(name="Test", R=0.2, S=0.5, C=0.6, L=0.05, M=0.0):
    ai = AIPlayer(name, "测试", R, S, C, L)
    ai.M = M
    return ai


class TestMakeDecision(unittest.TestCase):
    def test_p0_zero_always_self(self):
        ai = _make_ai(R=0.2)
        choice, bd = make_decision(ai, p0=0.0, opponent_name="Opp")
        self.assertEqual(choice, "self")

    def test_p0_one_always_opponent(self):
        ai = _make_ai(R=0.2)
        choice, bd = make_decision(ai, p0=1.0, opponent_name="Opp")
        self.assertEqual(choice, "opponent")

    def test_high_p0_attacks(self):
        ai = _make_ai(R=0.2, L=0.0)
        attack_count = 0
        for _ in range(50):
            choice, _ = make_decision(ai, p0=0.5, opponent_name="Opp")
            if choice == "opponent":
                attack_count += 1
            ai.last_choice = None
        self.assertGreater(attack_count, 30)

    def test_low_p0_self_targets(self):
        ai = _make_ai(R=0.8, L=0.0)
        self_count = 0
        for _ in range(50):
            choice, _ = make_decision(ai, p0=0.1, opponent_name="Opp")
            if choice == "self":
                self_count += 1
            ai.last_choice = None
        self.assertGreater(self_count, 30)

    def test_inertia_reuses_last_choice(self):
        """S=1.0, p0=0 时惯性 100%，必然复用上次选择。"""
        ai = _make_ai(S=1.0)
        ai.last_choice = "self"
        ai.loss_streak = 0
        for _ in range(20):
            choice, bd = make_decision(ai, p0=0.0, opponent_name="Opp")
            self.assertEqual(choice, "self")
            self.assertFalse(bd.reanalyzed)

    def test_positive_mindset_increases_attack(self):
        """亢奋心态增加攻击倾向 —— 需降低 C 避免冷静压制心态。"""
        ai_neutral = _make_ai(M=0.0, L=0.0, R=0.3, C=0.1)
        ai_high = _make_ai(M=0.8, L=0.0, R=0.3, C=0.1)
        neutral_attacks = 0
        high_attacks = 0
        for _ in range(30):
            n_choice, _ = make_decision(ai_neutral, p0=0.3, opponent_name="Opp")
            h_choice, _ = make_decision(ai_high, p0=0.3, opponent_name="Opp")
            if n_choice == "opponent":
                neutral_attacks += 1
            if h_choice == "opponent":
                high_attacks += 1
            ai_neutral.last_choice = None
            ai_high.last_choice = None
        self.assertGreater(high_attacks, neutral_attacks)

    def test_breakdown_has_all_fields(self):
        ai = _make_ai()
        _, bd = make_decision(ai, p0=0.5, opponent_name="Opp")
        d = bd.to_dict()
        for key in ("s_real", "reanalyzed", "pr", "base_attack",
                     "option_value",
                     "mindset_delta", "attack_after_mindset",
                     "calm_delta", "attack_after_calm",
                     "random_delta", "final_attack", "choice"):
            self.assertIn(key, d)

    def test_breakdown_skipped_when_inertia(self):
        """S=1.0, p0=0 时惯性 100%，reanalyzed=False。"""
        ai = _make_ai(S=1.0)
        ai.last_choice = "opponent"
        _, bd = make_decision(ai, p0=0.0, opponent_name="Opp")
        self.assertFalse(bd.reanalyzed)
        self.assertEqual(bd.base_attack, 0)
        self.assertEqual(bd.final_attack, 0)
