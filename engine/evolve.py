"""CMA-ES 人格约束进化（Phase 5）。

每位选手在 R/S/C/L 各自 ±30% 的参数域内做约束寻优：
  适应度 = 候选参数 vs 五名模板选手的循环赛胜率（其余五人保持模板值）
  搜索   = 标准 CMA-ES（4 维归一化坐标，候选裁剪到 [−1,1]）
  降噪   = 同代候选共用对局种子（Common Random Numbers）
  决赛   = 进化期 top-3 + 原始参数用大样本复评，取最优

进化为自私优化近似（各自在标准环境下寻优，非联合均衡）；
产出 benchmarks/evolved_params.json，默认模板不替换——保证既有基准可复现。

用法：
    python -m engine.evolve                          # 正式进化（~26 分钟）
    python -m engine.evolve --smoke                  # 冒烟（分钟级）
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from itertools import combinations
from pathlib import Path

import numpy as np

from .config import DEFAULT_MAX_CHARGES, get_player_templates
from .game import simulate_match
from .models import AIPlayer

PARAM_NAMES = ("R", "S", "C", "L")
# 人格约束：各参数相对模板值 ±30%
PARAM_PERTURB = 0.30


class CMAES:
    """标准 CMA-ES（Hansen 教程实现，最大化适应度接口）。"""

    def __init__(self, x0: np.ndarray, sigma: float, popsize: int):
        self.n = len(x0)
        self.popsize = popsize
        self.mu = popsize // 2
        self.x_mean = np.array(x0, dtype=float)
        self.sigma = sigma
        self.C = np.eye(self.n)
        self.B = np.eye(self.n)
        self.D = np.ones(self.n)
        self.p_c = np.zeros(self.n)
        self.p_sigma = np.zeros(self.n)
        self.count_eval = 0

        # 权重与策略常数
        w_raw = np.array([math.log(self.mu + 0.5) - math.log(i + 1)
                          for i in range(self.mu)])
        self.w = w_raw / w_raw.sum()
        self.mu_eff = 1.0 / (self.w ** 2).sum()
        n, mueff = self.n, self.mu_eff
        self.c_sigma = (mueff + 2) / (n + mueff + 3)
        self.d_sigma = 1 + 2 * max(0, math.sqrt((mueff - 1) / (n + 1)) - 1) + self.c_sigma
        self.c_c = 4 / (n + 4)
        self.c_1 = 2 / ((n + 1.3) ** 2 + mueff)
        self.c_mu = min(1 - self.c_1,
                        2 * (mueff - 2 + 1 / mueff) / ((n + 2) ** 2 + mueff))
        self.chi_n = math.sqrt(self.n) * (
            1 - 1 / (4 * self.n) + 1 / (21 * self.n ** 2))

    def _decompose(self) -> None:
        self.C = (self.C + self.C.T) / 2
        d2, self.B = np.linalg.eigh(self.C)
        self.D = np.sqrt(np.maximum(d2, 1e-12))

    def ask(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """采样一代候选：返回 (未裁剪解, 裁剪解)。评估用裁剪解，分布更新用未裁剪解。"""
        self._decompose()
        out = []
        for _ in range(self.popsize):
            z = np.random.standard_normal(self.n)
            y = self.B @ (self.D * z)
            x_raw = self.x_mean + self.sigma * y
            out.append((x_raw, np.clip(x_raw, -1.0, 1.0)))
        return out

    def tell(self, candidates: list[tuple[np.ndarray, np.ndarray]],
             fitness: list[float]) -> None:
        """按适应度降序选前 μ 更新分布（最大化问题）。"""
        order = list(np.argsort(fitness)[::-1][:self.mu])
        y_all = [(x_raw - self.x_mean) / self.sigma for x_raw, _ in candidates]

        y_w = np.zeros(self.n)
        x_w = np.zeros(self.n)
        for k, i in enumerate(order):
            y_w += self.w[k] * y_all[i]
            x_w += self.w[k] * candidates[i][1]

        Cinv_sqrt_y = self.B @ (np.divide(1, self.D, out=np.zeros(self.n),
                                          where=self.D > 0) * (self.B.T @ y_w))
        self.p_sigma = ((1 - self.c_sigma) * self.p_sigma
                        + math.sqrt(self.c_sigma * (2 - self.c_sigma) * self.mu_eff)
                        * Cinv_sqrt_y)
        h_sigma = 1.0 if (np.linalg.norm(self.p_sigma)
                          / math.sqrt(1 - (1 - self.c_sigma)
                                      ** (2 * (self.count_eval + 1)))
                          < 1.4 + 2 / (self.n + 1)) else 0.0
        self.p_c = ((1 - self.c_c) * self.p_c
                    + h_sigma * math.sqrt(self.c_c * (2 - self.c_c) * self.mu_eff) * y_w)

        rank_mu = sum(self.w[k] * np.outer(y_all[order[k]], y_all[order[k]])
                      for k in range(self.mu))
        delta_h = (1 - h_sigma) * self.c_c * (2 - self.c_c) * self.C
        self.C = ((1 - self.c_1 - self.c_mu) * self.C
                  + self.c_1 * (np.outer(self.p_c, self.p_c) + delta_h)
                  + self.c_mu * rank_mu)
        self.sigma *= math.exp((self.c_sigma / self.d_sigma)
                               * (np.linalg.norm(self.p_sigma) / self.chi_n - 1))
        self.x_mean = x_w
        self.count_eval += 1


def _candidate_seeds(base_seed: int, gen: int, tournaments: int) -> list[int]:
    """同代候选共用种子流（CRN）：参数差异是胜率差异的唯一来源。"""
    return [base_seed + gen * 7919 + i * 104729 for i in range(tournaments)]


def evaluate_params(target_name: str, params: tuple[float, float, float, float],
                    seeds: list[int], mode: str = "buckshot",
                    item_set: str = "full",
                    max_charges: int = DEFAULT_MAX_CHARGES) -> float:
    """候选参数 vs 五名模板选手的循环赛胜率（每届 5 场）。"""
    templates = get_player_templates()
    names = [t.name for t in templates]
    wins = games = 0
    for seed in seeds:
        rng = random.Random(seed)
        players: dict[str, AIPlayer] = {}
        for t in templates:
            if t.name == target_name:
                players[t.name] = AIPlayer(t.name, t.character, *params,
                                           max_charges=max_charges)
            else:
                players[t.name] = AIPlayer(t.name, t.character, t.R, t.S,
                                           t.C, t.L, max_charges=max_charges)
        for a, b in combinations(range(len(names)), 2):
            ia, ib = (a, b) if rng.random() < 0.5 else (b, a)
            winner = simulate_match(players[names[ia]], players[names[ib]],
                                    mode=mode, max_charges=max_charges,
                                    item_set=item_set, rng=rng)
            if winner.name == target_name:
                wins += 1
        games += len(names) - 1
    return wins / games if games else 0.0


def evolve_player(name: str, generations: int, popsize: int, tournaments: int,
                  base_seed: int, mode: str = "buckshot", item_set: str = "full",
                  finals_multiplier: int = 4) -> dict:
    """单选手 CMA-ES 进化：返回含轨迹与决赛结果的报告。"""
    t = next(t for t in get_player_templates() if t.name == name)
    center = np.array([t.R, t.S, t.C, t.L])
    radius = PARAM_PERTURB * center

    np.random.seed(base_seed ^ hash(name) & 0xFFFF)
    es = CMAES(np.zeros(4), sigma=0.35, popsize=popsize)
    history: list[tuple[tuple[float, ...], float]] = []

    for gen in range(generations):
        cand = es.ask()
        seeds = _candidate_seeds(base_seed, gen, tournaments)
        fits = [evaluate_params(name, tuple(center + radius * c), seeds,
                                mode=mode, item_set=item_set)
                for _, c in cand]
        es.tell(cand, fits)
        best_i = int(np.argmax(fits))
        history.append((tuple(center + radius * cand[best_i][1]), fits[best_i]))

    # 决赛：进化期 top-3 唯一参数 + 原始模板，大样本复评
    uniq: dict[tuple[float, ...], float] = {}
    for params, fit in history:
        uniq.setdefault(params, fit)
    finalists = sorted(uniq, key=uniq.get, reverse=True)[:3]
    original = tuple(center.tolist())
    finals_seeds = [base_seed + 500_000_007 + i
                    for i in range(tournaments * finals_multiplier)]
    scored = [(p, evaluate_params(name, p, finals_seeds, mode=mode,
                                  item_set=item_set))
              for p in finalists + [original]]
    best_params, best_fit = max(scored, key=lambda x: x[1])
    orig_fit = next(f for p, f in scored if p == original)

    deltas = [(p - o) / o * 100 for p, o in zip(best_params, original)]
    return {
        "name": name,
        "original": original,
        "evolved": best_params,
        "delta_pct": deltas,
        "fitness_original": orig_fit,
        "fitness_evolved": best_fit,
        "lift": best_fit - orig_fit,
        "in_domain": all(abs(d) <= PARAM_PERTURB * 100 + 1e-9 for d in deltas),
        "trajectory": history,
    }


def run_evolution(generations: int, popsize: int, tournaments: int,
                  finals_multiplier: int, base_seed: int,
                  out_json: Path, mode: str = "buckshot",
                  item_set: str = "full") -> dict:
    templates = get_player_templates()
    results = {}
    started = time.time()
    for idx, t in enumerate(templates):
        t0 = time.time()
        print(f"[{idx + 1}/6] {t.name}（{t.character}）进化中 "
              f"{generations}代×{popsize}候选×{tournaments}届 ...", flush=True)
        rep = evolve_player(t.name, generations, popsize, tournaments,
                            base_seed=base_seed + idx * 1_000_003,
                            mode=mode, item_set=item_set,
                            finals_multiplier=finals_multiplier)
        rep.pop("trajectory")
        results[t.name] = rep
        print(f"      原始 {rep['fitness_original']:.4f} → 进化 {rep['fitness_evolved']:.4f}"
              f" （+{rep['lift'] * 100:.2f}pp, {time.time() - t0:.0f}s）"
              f" ΔR{rep['delta_pct'][0]:+.0f}% ΔS{rep['delta_pct'][1]:+.0f}%"
              f" ΔC{rep['delta_pct'][2]:+.0f}% ΔL{rep['delta_pct'][3]:+.0f}%", flush=True)

    payload = {
        "meta": {
            "algorithm": "CMA-ES (standard, numpy)",
            "constraint": f"±{PARAM_PERTURB * 100:.0f}% per-parameter domain",
            "mode": mode, "item_set": item_set,
            "generations": generations, "popsize": popsize,
            "tournaments_per_eval": tournaments,
            "finals_multiplier": finals_multiplier,
            "seed": base_seed, "elapsed_sec": round(time.time() - started, 1),
        },
        "players": results,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n结果已写入 {out_json}（总耗时 {time.time() - started:.0f}s）", flush=True)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="CMA-ES 人格约束进化")
    parser.add_argument("--generations", type=int, default=16)
    parser.add_argument("--popsize", type=int, default=6)
    parser.add_argument("--tournaments", type=int, default=1000,
                        help="进化期每候选评估届数")
    parser.add_argument("--finals-multiplier", type=int, default=4,
                        help="决赛届数 = tournaments × multiplier")
    parser.add_argument("--seed", type=int, default=20260817)
    parser.add_argument("--mode", default="buckshot", choices=["buckshot"])
    parser.add_argument("--items", default="full", dest="item_set",
                        choices=["standard", "full"])
    parser.add_argument("--smoke", action="store_true",
                        help="冒烟：3代×4候选×60届")
    args = parser.parse_args()

    gens, pop, tours = args.generations, args.popsize, args.tournaments
    if args.smoke:
        gens, pop, tours = 3, 4, 60

    out = Path(__file__).resolve().parents[1] / "benchmarks" / "evolved_params.json"
    if args.smoke:
        out = out.with_name("evolved_params_smoke.json")

    run_evolution(gens, pop, tours, args.finals_multiplier, args.seed,
                  out, mode=args.mode, item_set=args.item_set)


if __name__ == "__main__":
    main()
