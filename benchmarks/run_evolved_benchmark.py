"""进化后参数验证（Phase 5）。

读取 evolved_params.json，用进化参数跑 10 万届 full+L2 基准，
对照 Phase 4 模板基准；并做 ±30% 域与行为签名检查。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.simulate import run_benchmark

ROOT = Path(__file__).resolve().parents[1]


def main(tournaments: int = 100000, seed: int = 20260817) -> None:
    payload = json.loads((ROOT / "benchmarks" / "evolved_params.json")
                         .read_text(encoding="utf-8"))
    overrides = {name: tuple(rep["evolved"])
                 for name, rep in payload["players"].items()}

    print("===== 进化后参数（±30% 域内）=====")
    for name, rep in payload["players"].items():
        p, o = rep["evolved"], rep["original"]
        print(f"{name:<10} R {o[0]:.3f}→{p[0]:.3f} ({rep['delta_pct'][0]:+.1f}%)"
              f"  S {o[1]:.3f}→{p[1]:.3f} ({rep['delta_pct'][1]:+.1f}%)"
              f"  C {o[2]:.3f}→{p[2]:.3f} ({rep['delta_pct'][2]:+.1f}%)"
              f"  L {o[3]:.3f}→{p[3]:.3f} ({rep['delta_pct'][3]:+.1f}%)"
              f"  进化期提升 {rep['lift'] * 100:+.2f}pp")

    print(f"\n===== 进化后基准（{tournaments} 届 × 15 场，full+L2）=====")
    rows = run_benchmark(mode="buckshot", tournaments=tournaments, seed=seed,
                         item_set="full", param_overrides=overrides)
    print(f"{'排名':<4}{'选手':<12}{'角色':<10}{'胜率':>8}{'平均排名':>10}{'夺冠':>10}")
    for r in rows:
        print(f"{r['rank']:<4}{r['name']:<12}{r['character']:<10}"
              f"{r['win_rate'] * 100:>7.1f}%{r['avg_rank']:>10.2f}{r['titles']:>10}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    main(n)
