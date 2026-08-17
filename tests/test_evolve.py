"""CMA-ES 人格约束进化测试（Phase 5）。

覆盖：CMA-ES 数学核心（sphere 收敛/裁剪/分布更新存活）、
适应度评估确定性（CRN）、单选手进化冒烟、±30% 人格域硬约束。
"""

from __future__ import annotations

import random
import unittest

import numpy as np

from engine.config import get_player_templates
from engine.evolve import (CMAES, PARAM_PERTURB, evaluate_params,
                           evolve_player)


class TestCMAESCore(unittest.TestCase):
    def test_sphere_convergence(self):
        # 4 维偏移 sphere：50 代内逼近已知最优点（最大化 -sphere）
        rng_state = np.random.get_state()
        np.random.seed(20260817)
        try:
            target = np.array([0.4, -0.3, 0.2, 0.1])
            es = CMAES(np.zeros(4), sigma=0.4, popsize=8)
            best_x, best_f = None, -np.inf
            for _ in range(50):
                cand = es.ask()
                fits = [-float(np.sum((x[1] - target) ** 2)) for x in cand]
                i = int(np.argmax(fits))
                if fits[i] > best_f:
                    best_f, best_x = fits[i], cand[i][1]
                es.tell(cand, fits)
            self.assertLess(np.linalg.norm(best_x - target), 0.25)
            self.assertGreater(best_f, -0.1)
        finally:
            np.random.set_state(rng_state)

    def test_candidates_clipped_to_domain(self):
        np.random.seed(7)
        es = CMAES(np.zeros(4), sigma=2.0, popsize=10)   # 大步长强制触界
        cand = es.ask()
        for x_raw, x_clip in cand:
            self.assertTrue(np.all(x_clip >= -1.0 - 1e-12))
            self.assertTrue(np.all(x_clip <= 1.0 + 1e-12))

    def test_covariance_stays_psd(self):
        np.random.seed(11)
        es = CMAES(np.zeros(4), sigma=0.3, popsize=6)
        for gen in range(8):
            cand = es.ask()
            fits = [random.random() for _ in cand]
            es.tell(cand, fits)
            eigs = np.linalg.eigvalsh((es.C + es.C.T) / 2)
            self.assertGreater(eigs.min(), -1e-10)
        self.assertGreater(es.sigma, 0)

    def test_step_adapts(self):
        # 收敛信号（都选中同一方向）应使步长收缩
        np.random.seed(3)
        es = CMAES(np.zeros(4), sigma=0.5, popsize=6)
        s0 = es.sigma
        for _ in range(10):
            cand = es.ask()
            fits = [-float(np.sum(x[1] ** 2)) for x in cand]
            es.tell(cand, fits)
        self.assertLess(es.sigma, s0)


class TestEvaluateParams(unittest.TestCase):
    def test_deterministic_under_same_seeds(self):
        t = get_player_templates()[0]
        params = (t.R, t.S, t.C, t.L)
        seeds = [101, 202, 303]
        f1 = evaluate_params(t.name, params, seeds)
        f2 = evaluate_params(t.name, params, seeds)
        self.assertEqual(f1, f2)

    def test_win_rate_range(self):
        t = get_player_templates()[0]
        f = evaluate_params(t.name, (t.R, t.S, t.C, t.L),
                            list(range(40)))
        self.assertGreaterEqual(f, 0.0)
        self.assertLessEqual(f, 1.0)


class TestEvolvePlayer(unittest.TestCase):
    def test_smoke_evolution_respects_domain(self):
        rng_state = np.random.get_state()
        np.random.seed(20260817)
        try:
            rep = evolve_player("GPT", generations=3, popsize=4,
                                tournaments=40, base_seed=99)
        finally:
            np.random.set_state(rng_state)
        t = next(t for t in get_player_templates() if t.name == "GPT")
        for evolved, original in zip(rep["evolved"], (t.R, t.S, t.C, t.L)):
            self.assertLessEqual(abs(evolved - original),
                                 PARAM_PERTURB * original + 1e-9)
        self.assertTrue(rep["in_domain"])
        self.assertGreaterEqual(rep["fitness_original"], 0.0)
        self.assertGreaterEqual(rep["fitness_evolved"], 0.0)


if __name__ == "__main__":
    unittest.main()
