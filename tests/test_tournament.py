"""RoundRobinRunner 锦标赛单元测试。"""

from __future__ import annotations

import unittest

from engine.tournament import RoundRobinRunner


class TestRoundRobinRunner(unittest.TestCase):
    def test_init_creates_schedule(self):
        runner = RoundRobinRunner(player_count=4, seed=42)
        self.assertEqual(runner.num_players, 4)
        self.assertEqual(runner.total_matches, 6)
        self.assertEqual(runner.match_index, 0)
        self.assertFalse(runner.is_over)

    def test_step_advances_match(self):
        runner = RoundRobinRunner(player_count=4, seed=42)
        runner.step()
        self.assertEqual(runner.match_index, 1)
        self.assertIsNotNone(runner.current_game)
        self.assertEqual(len(runner.match_results), 1)

    def test_run_all_completes(self):
        runner = RoundRobinRunner(player_count=4, seed=42)
        runner.run_all()
        self.assertTrue(runner.is_over)
        self.assertEqual(runner.match_index, 6)
        self.assertEqual(len(runner.ranking), 4)

    def test_wins_sum_to_matches(self):
        runner = RoundRobinRunner(player_count=6, seed=42)
        runner.run_all()
        self.assertEqual(sum(runner.wins), runner.total_matches)

    def test_ranking_is_sorted(self):
        runner = RoundRobinRunner(player_count=6, seed=42)
        runner.run_all()
        ranks = [r["rank"] for r in runner.ranking]
        self.assertEqual(ranks, sorted(ranks))

    def test_ranking_ties_have_same_rank(self):
        runner = RoundRobinRunner(player_count=6, seed=42)
        runner.run_all()
        for i in range(len(runner.ranking) - 1):
            r1 = runner.ranking[i]
            r2 = runner.ranking[i + 1]
            if r1["wins"] == r2["wins"]:
                self.assertEqual(r1["rank"], r2["rank"])

    def test_get_state_before_and_after(self):
        runner = RoundRobinRunner(player_count=4, seed=42)
        state_before = runner.get_state()
        self.assertEqual(state_before["match_index"], 0)
        self.assertFalse(state_before["is_over"])
        runner.run_all()
        state_after = runner.get_state()
        self.assertTrue(state_after["is_over"])

    def test_seed_determinism(self):
        r1 = RoundRobinRunner(player_count=4, seed=123)
        r1.run_all()
        r2 = RoundRobinRunner(player_count=4, seed=123)
        r2.run_all()
        self.assertEqual(r1.wins, r2.wins)
