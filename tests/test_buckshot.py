"""恶魔轮盘（Buckshot）模式单元测试：Shotgun / 效用决策 / 双模式会话 / 锦标赛 / 请求校验。"""

from __future__ import annotations

import random
import unittest

from engine.decision import make_utility_decision
from engine.factory import create_game, create_tournament
from engine.game import GameSession, simulate_match
from engine.models import AIPlayer, RouletteGun, Shotgun
from engine.tournament import RoundRobinRunner

try:
    import pydantic  # noqa: F401
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


def _make_ai(name, R=0.2, S=0.3, C=0.5, L=0.0, is_human=False, max_charges=None):
    return AIPlayer(name, "测试", R, S, C, L, is_human=is_human, max_charges=max_charges)


class TestShotgun(unittest.TestCase):
    def test_load_size_and_ratio_bounds(self):
        for _ in range(50):
            sg = Shotgun()
            self.assertGreaterEqual(sg.total_slots, 2)
            self.assertLessEqual(sg.total_slots, 8)
            self.assertGreaterEqual(sg.live_bullets, 1)
            self.assertGreaterEqual(sg.blank_bullets, 1)

    def test_public_counts_consistent(self):
        sg = Shotgun(rng=random.Random(7))
        for _ in range(sg.total_slots):
            live, blank = sg.get_counts()
            self.assertGreater(live + blank, 0)
            sg.shoot()
        self.assertTrue(sg.is_empty)
        self.assertEqual(sg.get_counts(), (0, 0))

    def test_reload_changes_ratio(self):
        sg = Shotgun(min_shells=8, max_shells=8, rng=random.Random(1))
        ratios = set()
        for _ in range(20):
            sg.reload()
            ratios.add((sg.live_bullets, sg.blank_bullets))
        self.assertGreater(len(ratios), 1)  # 配比逐次随机

    def test_peek_matches_shoot(self):
        sg = Shotgun(rng=random.Random(3))
        results = [(sg.peek(), sg.shoot()) for _ in range(sg.total_slots)]
        for peeked, fired in results:
            self.assertEqual(peeked, fired)

    def test_p0_in_range(self):
        sg = Shotgun(rng=random.Random(11))
        while not sg.is_empty:
            p0 = sg.get_p0()
            self.assertGreater(p0, 0.0)
            self.assertLessEqual(p0, 1.0)  # 空弹耗尽后可能只剩实弹 → p0=1
            sg.shoot()

    def test_determinism_with_seed(self):
        a = Shotgun(rng=random.Random(42))
        b = Shotgun(rng=random.Random(42))
        seq_a = [a.shoot() for _ in range(a.total_slots)] + [a.reload() or a.shoot()]
        seq_b = [b.shoot() for _ in range(b.total_slots)] + [b.reload() or b.shoot()]
        self.assertEqual(seq_a, seq_b)

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            Shotgun(min_shells=1)
        with self.assertRaises(ValueError):
            Shotgun(min_shells=6, max_shells=4)

    def test_to_dict_structure(self):
        d = Shotgun(rng=random.Random(5)).to_dict()
        for key in ("total_slots", "live_bullets", "blank_bullets",
                    "pointer", "remaining_live", "remaining_blank", "remaining_slots"):
            self.assertIn(key, d)


class TestCharges(unittest.TestCase):
    def test_take_damage_decrements_and_kills(self):
        ai = _make_ai("A", max_charges=3)
        self.assertFalse(ai.take_damage(1))
        self.assertEqual(ai.charges, 2)
        self.assertTrue(ai.is_alive)
        self.assertTrue(ai.take_damage(2))  # 电荷归零 → 被击倒
        self.assertEqual(ai.charges, 0)
        self.assertFalse(ai.is_alive)

    def test_prepare_resets_charges(self):
        ai = _make_ai("A", max_charges=3)
        ai.take_damage(3)
        ai.prepare_for_match("B")
        self.assertEqual(ai.charges, 3)
        self.assertTrue(ai.is_alive)

    def test_classic_player_has_null_charges(self):
        ai = _make_ai("A")
        self.assertIsNone(ai.max_charges)
        self.assertIsNone(ai.charges)


class TestUtilityDecision(unittest.TestCase):
    def test_known_blank_always_self(self):
        ai = _make_ai("A")
        choice, bd = make_utility_decision(ai, p_live=0.0, my_charges=3, opp_charges=3)
        self.assertEqual(choice, "self")
        self.assertTrue(bd.reanalyzed)

    def test_known_live_always_opponent(self):
        ai = _make_ai("A")
        choice, _ = make_utility_decision(ai, p_live=1.0, my_charges=3, opp_charges=3)
        self.assertEqual(choice, "opponent")

    def test_blank_majority_favors_self_for_gambler(self):
        """空弹居多时，高 R 赌徒（重蝉联期权）倾向自击，低 R 谨慎者倾向攻击。"""
        cautious = _make_ai("Claude", R=0.16)
        gambler = _make_ai("DeepSeek", R=0.32)
        c_choice, _ = make_utility_decision(cautious, p_live=0.34, my_charges=3, opp_charges=3)
        g_choice, _ = make_utility_decision(gambler, p_live=0.34, my_charges=3, opp_charges=3)
        self.assertEqual(c_choice, "opponent")
        self.assertEqual(g_choice, "self")

    def test_behind_in_charges_increases_aggression(self):
        """电荷落后时回合权价值上升 → 同概率下更倾向自击换蝉联。"""
        ai = _make_ai("A", R=0.2)
        _, bd_even = make_utility_decision(ai, p_live=0.4, my_charges=3, opp_charges=3)
        _, bd_behind = make_utility_decision(ai, p_live=0.4, my_charges=1, opp_charges=3)
        self.assertLess(bd_behind.final_diff, bd_even.final_diff)

    def test_inertia_reuses_last_choice(self):
        """S=1.0 且 p=0 时惯性 100%，必然复用上次选择（与经典模式同构）。"""
        ai = _make_ai("A", S=1.0)
        ai.last_choice = "self"
        ai.loss_streak = 0
        choice, bd = make_utility_decision(ai, p_live=0.0, my_charges=3, opp_charges=3)
        self.assertEqual(choice, "self")
        self.assertFalse(bd.reanalyzed)

    def test_breakdown_fields(self):
        ai = _make_ai("A")
        _, bd = make_utility_decision(ai, p_live=0.5, my_charges=3, opp_charges=3)
        d = bd.to_dict()
        for key in ("kernel", "s_real", "p_live", "t_value", "lam_kill", "lam_own",
                    "lam_give", "eu_self", "eu_enemy", "raw_diff",
                    "mindset_delta", "calm_factor", "noise_delta", "final_diff", "choice"):
            self.assertIn(key, d)


class TestBuckshotSession(unittest.TestCase):
    def test_mode_selects_shotgun_and_charges(self):
        p1, p2 = _make_ai("A"), _make_ai("B")
        gs = GameSession(p1, p2, mode="buckshot", max_charges=3)
        self.assertIsInstance(gs.gun, Shotgun)
        self.assertEqual(p1.max_charges, 3)
        self.assertEqual(p2.charges, 3)
        self.assertEqual(gs.get_state()["mode"], "buckshot")

    def test_classic_mode_unchanged(self):
        p1, p2 = _make_ai("A"), _make_ai("B")
        gs = GameSession(p1, p2)
        self.assertIsInstance(gs.gun, RouletteGun)
        self.assertIsNone(p1.max_charges)

    def test_unknown_mode_rejected(self):
        p1, p2 = _make_ai("A"), _make_ai("B")
        with self.assertRaises(ValueError):
            GameSession(p1, p2, mode="nonsense")

    def test_auto_play_terminates_with_dead_loser(self):
        p1, p2 = _make_ai("A"), _make_ai("B")
        gs = GameSession(p1, p2, mode="buckshot")
        gs.auto_play_to_end()
        self.assertTrue(gs.is_over)
        self.assertIsNotNone(gs.winner)
        loser = p2 if gs.winner is p1 else p1
        self.assertFalse(loser.is_alive)
        self.assertEqual(loser.charges, 0)
        self.assertGreaterEqual(gs.winner.charges, 1)

    def test_turn_passes_after_live_self_shot_survival(self):
        """自击实弹但存活 → 电荷-1 且回合移交（与经典模式的关键差异）。"""
        p1, p2 = _make_ai("A"), _make_ai("B")
        gs = GameSession(p1, p2, mode="buckshot", max_charges=3)
        gs.gun.chamber = [True, False, False]  # 当前弹必为实弹
        gs.gun.total_slots = 3
        gs.gun.pointer = 0
        gs._execute_shot("self")
        self.assertEqual(p1.charges, 2)
        self.assertIs(gs.current, p2)  # 回合移交

    def test_blank_self_shot_keeps_turn(self):
        p1, p2 = _make_ai("A"), _make_ai("B")
        gs = GameSession(p1, p2, mode="buckshot")
        gs.gun.chamber = [False, True, False]
        gs.gun.pointer = 0
        gs._execute_shot("self")
        self.assertEqual(p1.charges, 3)
        self.assertIs(gs.current, p1)  # 蝉联

    def test_reload_event_announces_public_counts(self):
        p1, p2 = _make_ai("A"), _make_ai("B")
        gs = GameSession(p1, p2, mode="buckshot", rng=random.Random(9))
        while not gs.gun.is_empty and not gs.is_over:
            gs._do_step()
        reload_events = [e for e in gs.events if e.type == "result" and "重新装填" in (e.message or "")]
        self.assertGreaterEqual(len(reload_events), 1)

    def test_human_action_flow_buckshot(self):
        p1 = _make_ai("Human", is_human=True, max_charges=3)
        p2 = _make_ai("Bot")
        gs = GameSession(p1, p2, mode="buckshot")
        state = gs.human_action("opponent")
        self.assertGreaterEqual(gs.turn_count, 1)
        self.assertIn("mode", state)

    def test_determinism_with_rng(self):
        def run():
            p1, p2 = _make_ai("A"), _make_ai("B")
            gs = GameSession(p1, p2, mode="buckshot", rng=random.Random(77))
            gs.auto_play_to_end()
            return gs.winner.name, p1.charges, p2.charges
        self.assertEqual(run(), run())

    def test_factory_creates_buckshot_game(self):
        gs = create_game("Claude", "DeepSeek", mode="buckshot", max_charges=4)
        self.assertEqual(gs.mode, "buckshot")
        self.assertEqual(gs.p1.max_charges, 4)
        self.assertIsInstance(gs.gun, Shotgun)


class TestBuckshotSimulateAndTournament(unittest.TestCase):
    def test_simulate_match_buckshot_returns_winner(self):
        p1 = _make_ai("A", max_charges=3)
        p2 = _make_ai("B", max_charges=3)
        winner = simulate_match(p1, p2, mode="buckshot")
        self.assertIn(winner, (p1, p2))
        self.assertEqual(min(p1.charges, p2.charges), 0)

    def test_tournament_buckshot_completes(self):
        runner = RoundRobinRunner(player_count=4, seed=42, mode="buckshot")
        runner.run_all()
        self.assertTrue(runner.is_over)
        self.assertEqual(sum(runner.wins), runner.total_matches)
        for p in runner.players:
            self.assertIsNotNone(p.max_charges)

    def test_tournament_seed_does_not_touch_global_random(self):
        before = random.getstate()
        RoundRobinRunner(player_count=4, seed=123, mode="buckshot").run_all()
        after = random.getstate()
        self.assertEqual(before, after)  # 全局随机状态不受污染

    def test_factory_tournament_buckshot(self):
        runner = create_tournament(player_count=4, mode="buckshot", max_charges=2)
        runner.step()
        self.assertEqual(runner.mode, "buckshot")


@unittest.skipUnless(HAS_PYDANTIC, "pydantic 未安装（无网络环境），跳过请求校验测试")
class TestSchemaValidation(unittest.TestCase):
    def test_zero_slots_rejected(self):
        from pydantic import ValidationError
        from server.schemas import CreateGameRequest
        with self.assertRaises(ValidationError):
            CreateGameRequest(player1="A", player2="B", total_slots=0)

    def test_bullets_exceeding_slots_rejected(self):
        from pydantic import ValidationError
        from server.schemas import CreateGameRequest
        with self.assertRaises(ValidationError):
            CreateGameRequest(player1="A", player2="B", total_slots=2, live_bullets=3)

    def test_bad_mode_rejected(self):
        from pydantic import ValidationError
        from server.schemas import CreateGameRequest
        with self.assertRaises(ValidationError):
            CreateGameRequest(player1="A", player2="B", mode="turbo")

    def test_bad_action_rejected(self):
        from pydantic import ValidationError
        from server.schemas import HumanActionRequest
        with self.assertRaises(ValidationError):
            HumanActionRequest(choice="reload")

    def test_buckshot_request_accepted(self):
        from server.schemas import CreateGameRequest
        req = CreateGameRequest(player1="A", player2="B", mode="buckshot", max_charges=4)
        self.assertEqual(req.mode, "buckshot")

    def test_tournament_player_count_bounds(self):
        from pydantic import ValidationError
        from server.schemas import CreateTournamentRequest
        with self.assertRaises(ValidationError):
            CreateTournamentRequest(player_count=1)
        with self.assertRaises(ValidationError):
            CreateTournamentRequest(player_count=9)

    def test_item_set_invalid_rejected(self):
        from pydantic import ValidationError
        from server.schemas import CreateGameRequest
        with self.assertRaises(ValidationError):
            CreateGameRequest(player1="A", player2="B", mode="buckshot",
                              item_set="mega")   # 未知道具集

    def test_full_item_set_accepted(self):
        from server.schemas import CreateGameRequest
        req = CreateGameRequest(player1="A", player2="B", mode="buckshot",
                                item_set="full")
        self.assertEqual(req.item_set, "full")   # Phase 3 DoN 道具集

    def test_classic_forces_item_set_none(self):
        from server.schemas import CreateGameRequest
        req = CreateGameRequest(player1="A", player2="B", mode="classic",
                                item_set="standard")
        self.assertEqual(req.item_set, "none")   # 与引擎归一规则一致

    def test_dual_action_forms(self):
        from pydantic import ValidationError
        from server.schemas import HumanActionRequest
        self.assertEqual(HumanActionRequest(choice="self").choice, "self")
        self.assertEqual(HumanActionRequest(item_id="beer").item_id, "beer")
        with self.assertRaises(ValidationError):
            HumanActionRequest()                              # 两者都缺
        with self.assertRaises(ValidationError):
            HumanActionRequest(choice="self", item_id="beer")  # 两者都给
