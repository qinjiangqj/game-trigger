"""大规模蒙特卡洛基准模拟。

用法：
    python -m engine.simulate                        # 经典模式 10 万场锦标赛
    python -m engine.simulate --mode buckshot        # 恶魔轮盘（无道具对照）
    python -m engine.simulate --mode buckshot --items standard
"""

from __future__ import annotations

import argparse
import random
import time
from itertools import combinations

from .config import DEFAULT_MAX_CHARGES, DEFAULT_ITEM_SET, get_player_templates
from .game import simulate_match
from .models import AIPlayer


def run_benchmark(mode: str = "classic", tournaments: int = 100000, seed: int = 20260817,
                  max_charges: int = DEFAULT_MAX_CHARGES,
                  item_set: str = "none",
                  param_overrides: dict[str, tuple[float, float, float, float]] | None = None
                  ) -> list[dict]:
    """运行 N 届循环赛（每届 6 人 15 场），返回按胜率降序的统计表。

    param_overrides：选手名 → (R, S, C, L) 覆盖模板参数（进化后验证用）。
    """
    rng = random.Random(seed)
    templates = get_player_templates()
    names = [t.name for t in templates]
    n = len(names)
    pairs = list(combinations(range(n), 2))

    wins = {name: 0 for name in names}
    games = {name: 0 for name in names}
    rank_sum = {name: 0 for name in names}
    titles = {name: 0 for name in names}

    charges = max_charges if mode == "buckshot" else None
    started = time.time()

    for tour in range(tournaments):
        players = {t.name: AIPlayer(t.name, t.character,
                                    *(param_overrides[t.name]
                                      if param_overrides and t.name in param_overrides
                                      else (t.R, t.S, t.C, t.L)),
                                    max_charges=charges) for t in templates}
        tour_wins = {name: 0 for name in names}
        for a, b in pairs:
            ia, ib = (a, b) if rng.random() < 0.5 else (b, a)  # 先手随机
            winner = simulate_match(players[names[ia]], players[names[ib]],
                                    mode=mode, max_charges=max_charges,
                                    item_set=item_set, rng=rng)
            tour_wins[winner.name] += 1

        for name in names:
            wins[name] += tour_wins[name]
            games[name] += n - 1
        ranking = sorted(names, key=lambda x: tour_wins[x], reverse=True)
        titles[ranking[0]] += 1
        for rank, name in enumerate(ranking, start=1):
            rank_sum[name] += rank

        if (tour + 1) % max(1, tournaments // 10) == 0:
            elapsed = time.time() - started
            tag = f"{mode}/items={item_set}" if item_set != "none" else mode
            print(f"  [{tag}] {tour + 1}/{tournaments} 届完成 ({elapsed:.1f}s)", flush=True)

    rows = []
    ranking = sorted(names, key=lambda x: wins[x], reverse=True)
    for rank, name in enumerate(ranking, start=1):
        rows.append({
            "rank": rank,
            "name": name,
            "character": next(t.character for t in templates if t.name == name),
            "win_rate": wins[name] / games[name] if games[name] else 0.0,
            "avg_rank": rank_sum[name] / tournaments,
            "titles": titles[name],
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 轮盘大逃杀基准模拟")
    parser.add_argument("--mode", choices=["classic", "buckshot", "duel"], default="classic")
    parser.add_argument("-n", "--tournaments", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=20260817)
    parser.add_argument("--max-charges", type=int, default=DEFAULT_MAX_CHARGES)
    parser.add_argument("--items", default="none", dest="item_set",
                        choices=["none", "standard", "full"],
                        help="道具集：none=无道具，standard=5 标准道具，full=9 全道具")
    args = parser.parse_args()

    items_tag = " · 道具=" + args.item_set if (args.mode == "buckshot" and args.item_set != "none") else ""
    print(f"开始模拟：{args.tournaments} 届循环赛 · mode={args.mode}{items_tag}", flush=True)
    rows = run_benchmark(mode=args.mode, tournaments=args.tournaments,
                         seed=args.seed, max_charges=args.max_charges,
                         item_set=args.item_set)

    label = {"classic": "经典轮盘", "buckshot": "恶魔轮盘", "duel": "决斗轮盘（各持一把）"}[args.mode]
    if args.mode == "buckshot" and args.item_set != "none":
        label += "（带道具）"
    print(f"\n===== {label} 基准胜率表（{args.tournaments} 届 × 15 场）=====")
    print(f"{'排名':<4}{'选手':<12}{'角色':<10}{'胜率':>8}{'平均排名':>10}{'夺冠':>10}")
    for r in rows:
        print(f"{r['rank']:<4}{r['name']:<12}{r['character']:<10}"
              f"{r['win_rate'] * 100:>7.1f}%{r['avg_rank']:>10.2f}{r['titles']:>10}")


if __name__ == "__main__":
    main()
