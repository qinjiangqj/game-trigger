"""AIPlayer 与 RouletteGun 模型单元测试。"""

from __future__ import annotations

import unittest

from engine.models import AIPlayer, RouletteGun


class TestRouletteGun(unittest.TestCase):
    def test_init_distributes_bullets(self):
        gun = RouletteGun(total_slots=6, live_bullets=2)
        self.assertEqual(sum(gun.chamber), 2)
        self.assertEqual(len(gun.chamber), 6)
        self.assertEqual(gun.pointer, 0)

    def test_get_p0_all_slots_remaining(self):
        gun = RouletteGun(total_slots=6, live_bullets=1)
        self.assertGreater(gun.get_p0(), 0)
        self.assertLess(gun.get_p0(), 1)

    def test_shoot_advances_pointer(self):
        gun = RouletteGun(total_slots=6, live_bullets=1)
        gun.shoot()
        self.assertEqual(gun.pointer, 1)

    def test_shoot_returns_bool(self):
        gun = RouletteGun(total_slots=6, live_bullets=6)
        self.assertTrue(gun.shoot())

    def test_shoot_all_empty(self):
        gun = RouletteGun(total_slots=6, live_bullets=1)
        gun.chamber = [False] * 6
        gun.pointer = 0
        self.assertFalse(gun.shoot())

    def test_shoot_raises_when_empty_chamber(self):
        gun = RouletteGun(total_slots=2, live_bullets=1)
        gun.shoot()
        gun.shoot()
        with self.assertRaises(RuntimeError):
            gun.shoot()

    def test_reload_resets_pointer(self):
        gun = RouletteGun(total_slots=6, live_bullets=1)
        for _ in range(6):
            gun.shoot()
        gun.reload()
        self.assertEqual(gun.pointer, 0)
        self.assertEqual(sum(gun.chamber), 1)

    def test_get_remaining(self):
        gun = RouletteGun(total_slots=6, live_bullets=2)
        gun.shoot()
        live, slots = gun.get_remaining()
        self.assertEqual(slots, 5)
        self.assertIn(live, (1, 2))

    def test_to_dict_structure(self):
        gun = RouletteGun(total_slots=6, live_bullets=1)
        d = gun.to_dict()
        for key in ("total_slots", "live_bullets", "pointer",
                     "remaining_live", "remaining_slots"):
            self.assertIn(key, d)

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            RouletteGun(total_slots=6, live_bullets=0)
        with self.assertRaises(ValueError):
            RouletteGun(total_slots=2, live_bullets=3)


class TestAIPlayer(unittest.TestCase):
    def test_init_defaults(self):
        ai = AIPlayer("Test", "测试", 0.2, 0.5, 0.6)
        self.assertEqual(ai.name, "Test")
        self.assertEqual(ai.M, 0.0)
        self.assertTrue(ai.is_alive)
        self.assertIsNone(ai.last_choice)
        self.assertEqual(ai.win_streak, 0)
        self.assertEqual(ai.loss_streak, 0)

    def test_prepare_for_match_resets_state(self):
        ai = AIPlayer("Test", "测试", 0.2, 0.5, 0.6)
        ai.M = 0.5
        ai.is_alive = False
        ai.last_choice = "self"
        ai.prepare_for_match("opponent")
        self.assertTrue(ai.is_alive)
        self.assertIsNone(ai.last_choice)
        self.assertAlmostEqual(ai.M, 0.5 * 0.7)

    def test_update_mindset_win(self):
        ai = AIPlayer("Test", "测试", 0.2, 0.5, 0.6)
        ai.update_mindset("win")
        # win_streak 先增至 1，M += 0.08 + 0.02 * 1 = 0.10
        self.assertAlmostEqual(ai.M, 0.10)
        self.assertEqual(ai.win_streak, 1)
        self.assertEqual(ai.loss_streak, 0)
        ai.update_mindset("win")
        # win_streak 增至 2，M += 0.08 + 0.02 * 2 = 0.12 → M = 0.22
        self.assertAlmostEqual(ai.M, 0.22)

    def test_update_mindset_loss(self):
        ai = AIPlayer("Test", "测试", 0.2, 0.5, 0.6)
        ai.update_mindset("loss")
        # loss_streak 先增至 1，M -= 0.10 + 0.03 * 1 = 0.13
        self.assertAlmostEqual(ai.M, -0.13)
        self.assertEqual(ai.loss_streak, 1)
        self.assertEqual(ai.win_streak, 0)

    def test_update_mindset_rest(self):
        ai = AIPlayer("Test", "测试", 0.2, 0.5, 0.6)
        ai.M = 0.5
        ai.update_mindset("rest")
        self.assertAlmostEqual(ai.M, 0.5 * 0.8)

    def test_mindset_clamped(self):
        ai = AIPlayer("Test", "测试", 0.2, 0.5, 0.6)
        for _ in range(50):
            ai.update_mindset("win")
        self.assertAlmostEqual(ai.M, 1.0)
        for _ in range(50):
            ai.update_mindset("loss")
        self.assertAlmostEqual(ai.M, -1.0)

    def test_to_dict_keys(self):
        ai = AIPlayer("Test", "测试", 0.2, 0.5, 0.6)
        d = ai.to_dict()
        for key in ("name", "character", "R", "S", "C", "L", "M",
                     "is_alive", "is_human", "last_choice",
                     "win_streak", "loss_streak"):
            self.assertIn(key, d)
