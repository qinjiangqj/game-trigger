"""决斗轮盘（duel）模式测试：各持一把独立弹巢，保留自击/击敌决策。"""

import random
import unittest

from engine.factory import create_game
from engine.game import GameSession, simulate_match
from engine.models import AIPlayer

try:
    from server.schemas import CreateGameRequest
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


def _human_pair():
    p1 = AIPlayer("A", "甲", 0.5, 0.0, 1.0, 0.0, is_human=True)
    p2 = AIPlayer("B", "乙", 0.5, 0.0, 1.0, 0.0, is_human=True)
    return p1, p2


def _duel_session(chambers1, chambers2):
    """构造 duel 对局并直接指定双方弹巢序列（可控结果）。"""
    p1, p2 = _human_pair()
    g = GameSession(p1, p2, mode="duel", rng=random.Random(0))
    for name, chambers in ((p1.name, chambers1), (p2.name, chambers2)):
        g._guns[name].chamber = list(chambers)
        g._guns[name].pointer = 0
    return g, p1, p2


class TestDuelSession(unittest.TestCase):

    def test_independent_guns_created(self):
        g = create_game("Claude", "GPT", mode="duel", total_slots=6, live_bullets=1)
        self.assertEqual(set(g._guns.keys()), {"Claude", "GPT"})
        for gun in g._guns.values():
            self.assertEqual(gun.total_slots, 6)
            self.assertEqual(gun.live_bullets, 1)
        # 先手行动：gun 属性指向先手自己的枪
        self.assertIs(g.gun, g._guns["Claude"])

    def test_classic_still_shared_gun(self):
        g = create_game("Claude", "GPT", mode="classic")
        self.assertIsNone(g._guns)
        self.assertIsNotNone(g._shared_gun)
        self.assertNotIn("guns", g.get_state())

    def test_item_set_normalized_to_none(self):
        g = create_game("Claude", "GPT", mode="duel", item_set="full")
        self.assertEqual(g.item_set, "none")

    def test_self_blank_keeps_turn_own_gun_only(self):
        g, p1, p2 = _duel_session([False] * 6, [False] * 6)
        g.human_action("self")
        self.assertIs(g.current, p1)          # 蝉联
        self.assertEqual(g._guns[p1.name].pointer, 1)
        self.assertEqual(g._guns[p2.name].pointer, 0)   # 对手的枪未被击发

    def test_self_live_loses(self):
        g, p1, p2 = _duel_session([True] + [False] * 5, [False] * 6)
        g.human_action("self")
        self.assertTrue(g.is_over)
        self.assertIs(g.winner, p2)

    def test_enemy_live_wins_with_own_gun(self):
        g, p1, p2 = _duel_session([True] + [False] * 5, [False] * 6)
        g.human_action("opponent")
        self.assertTrue(g.is_over)
        self.assertIs(g.winner, p1)
        self.assertEqual(g._guns[p1.name].pointer, 1)   # 击发的是自己的枪
        self.assertEqual(g._guns[p2.name].pointer, 0)

    def test_enemy_blank_swaps_to_opponent_own_gun(self):
        g, p1, p2 = _duel_session([False] * 6, [False, True] + [False] * 4)
        g.human_action("opponent")
        self.assertIs(g.current, p2)
        self.assertIs(g.gun, g._guns[p2.name])          # 换手后击发对手自己的枪

    def test_reload_only_shooters_gun(self):
        g, p1, p2 = _duel_session([False] * 6, [False] * 6)
        g._guns[p1.name].pointer = 5                    # 仅剩一发（空弹）
        g.human_action("self")                          # 空弹蝉联且弹巢打空 → 重装
        self.assertEqual(g._guns[p1.name].pointer, 0)
        self.assertEqual(g._guns[p1.name].live_bullets, 1)
        self.assertEqual(g._guns[p2.name].pointer, 0)
        msgs = [e.message for e in g.events if e.type == "result"]
        self.assertTrue(any("A 的弹巢打空" in m for m in msgs))

    def test_state_exposes_both_guns(self):
        g = create_game("Claude", "GPT", mode="duel")
        state = g.get_state()
        self.assertEqual(set(state["guns"].keys()), {"Claude", "GPT"})
        self.assertEqual(state["gun"]["total_slots"], 6)

    def test_duel_session_terminates(self):
        rng = random.Random(9)
        for _ in range(200):
            p1 = AIPlayer("A", "甲", 0.2, 0.5, 0.5, 0.05)
            p2 = AIPlayer("B", "乙", 0.3, 0.3, 0.5, 0.05)
            g = GameSession(p1, p2, mode="duel", rng=rng)
            g.auto_play_to_end()
            self.assertTrue(g.is_over)
            self.assertIn(g.winner.name, ("A", "B"))


class TestDuelSimulation(unittest.TestCase):

    def test_simulate_match_deterministic_with_seed(self):
        a1, b1 = AIPlayer("A", "甲", 0.2, 0.5, 0.5), AIPlayer("B", "乙", 0.3, 0.3, 0.5)
        a2, b2 = AIPlayer("A", "甲", 0.2, 0.5, 0.5), AIPlayer("B", "乙", 0.3, 0.3, 0.5)
        w1 = simulate_match(a1, b1, mode="duel", rng=random.Random(77))
        w2 = simulate_match(a2, b2, mode="duel", rng=random.Random(77))
        self.assertEqual(w1.name, w2.name)

    def test_simulate_match_both_sides_can_win(self):
        rng = random.Random(11)
        winners = set()
        for _ in range(500):
            a = AIPlayer("A", "甲", 0.2, 0.5, 0.5)
            b = AIPlayer("B", "乙", 0.3, 0.3, 0.5)
            winners.add(simulate_match(a, b, mode="duel", rng=rng).name)
        self.assertEqual(winners, {"A", "B"})


@unittest.skipUnless(HAS_PYDANTIC, "pydantic 未安装（无网络环境），跳过请求校验测试")
class TestDuelSchema(unittest.TestCase):

    def test_duel_mode_accepted_and_item_normalized(self):
        req = CreateGameRequest(player1="Claude", player2="GPT",
                                mode="duel", item_set="full")
        self.assertEqual(req.item_set, "none")

    def test_duel_rejects_overflow_bullets(self):
        with self.assertRaises(ValueError):
            CreateGameRequest(player1="Claude", player2="GPT",
                              mode="duel", total_slots=6, live_bullets=7)


if __name__ == "__main__":
    unittest.main()
