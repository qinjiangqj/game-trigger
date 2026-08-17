"""GameSession 对局流程单元测试。"""

from __future__ import annotations

import unittest

from engine.game import GameSession, simulate_match
from engine.models import AIPlayer


def _make_ai(name, R=0.2, S=0.3, C=0.5, L=0.05, is_human=False):
    return AIPlayer(name, "测试", R, S, C, L, is_human=is_human)


class TestGameSession(unittest.TestCase):
    def test_init_sets_players(self):
        p1 = _make_ai("A")
        p2 = _make_ai("B")
        gs = GameSession(p1, p2)
        self.assertIs(gs.p1, p1)
        self.assertIs(gs.p2, p2)
        self.assertIs(gs.current, p1)
        self.assertIs(gs.opponent, p2)
        self.assertFalse(gs.is_over)

    def test_ai_step_produces_events(self):
        p1 = _make_ai("A")
        p2 = _make_ai("B")
        gs = GameSession(p1, p2)
        gs.ai_step()
        self.assertGreaterEqual(len(gs.events), 2)
        self.assertGreaterEqual(gs.turn_count, 1)

    def test_human_action_requires_choice(self):
        p1 = _make_ai("Human", is_human=True)
        p2 = _make_ai("Bot")
        gs = GameSession(p1, p2)
        gs.human_action("self")
        self.assertGreaterEqual(len(gs.events), 2)

    def test_human_action_rejects_bad_choice(self):
        p1 = _make_ai("Human", is_human=True)
        p2 = _make_ai("Bot")
        gs = GameSession(p1, p2)
        with self.assertRaises(ValueError):
            gs.human_action("invalid")

    def test_auto_play_to_end_finishes(self):
        p1 = _make_ai("A")
        p2 = _make_ai("B")
        gs = GameSession(p1, p2)
        gs.auto_play_to_end()
        self.assertTrue(gs.is_over)
        self.assertIsNotNone(gs.winner)

    def test_get_state_has_keys(self):
        p1 = _make_ai("A")
        p2 = _make_ai("B")
        gs = GameSession(p1, p2)
        state = gs.get_state()
        for key in ("id", "p1", "p2", "gun", "current_player",
                     "opponent_player", "is_over", "winner",
                     "turn_count", "needs_human_input", "events"):
            self.assertIn(key, state)

    def test_gun_reloads_when_exhausted(self):
        from engine.models import RouletteGun
        gun = RouletteGun(total_slots=3, live_bullets=1)
        for _ in range(3):
            gun.shoot()
        self.assertEqual(gun.pointer, 3)
        gun.reload()
        self.assertEqual(gun.pointer, 0)
        self.assertEqual(sum(gun.chamber), 1)
        self.assertEqual(len(gun.chamber), 3)


class TestSimulateMatch(unittest.TestCase):
    def test_returns_winner(self):
        p1 = _make_ai("A")
        p2 = _make_ai("B")
        winner = simulate_match(p1, p2)
        self.assertIn(winner, (p1, p2))

    def test_updates_mindset(self):
        p1 = _make_ai("A")
        p2 = _make_ai("B")
        p1.M = 0.0
        p2.M = 0.0
        simulate_match(p1, p2)
        self.assertTrue(p1.M != 0.0 or p2.M != 0.0)
