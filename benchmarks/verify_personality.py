"""人格差异化验证（Phase 4 L2+）。

小规模模拟统计各选手行为签名：防御性道具使用、行为推断触发率、
对手建模读数分布——验证 L2 机制不会把六位人格磨成同一副面孔。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import get_player_templates
from engine.game import simulate_match


def main(n_matches: int = 5000, seed: int = 20260817) -> None:
    rng = random.Random(seed)
    names = [t.name for t in get_player_templates()]
    players = {name: dict(shots=0, attacks=0, items=0, threat_sum=0.0,
                          threat_reads=0, hi_shots=0, hi_attacks=0)
               for name in names}
    turns_total = 0

    for i in range(n_matches):
        a = names[rng.randrange(len(names))]
        b = names[rng.randrange(len(names))]
        if a == b:
            continue
        # 用带事件流的 GameSession 才能观测 breakdown；轻量版只取胜负
        from engine.factory import create_player
        from engine.game import GameSession
        pa, pb = create_player(a), create_player(b)
        g = GameSession(pa, pb, mode="buckshot", item_set="full",
                        rng=random.Random(rng.random()))
        g.auto_play_to_end()
        turns_total += g.turn_count
        for e in g.events:
            if e.type == "decision" and e.breakdown:
                stat = players[e.player_name]
                stat["shots"] += 1
                if e.action == "opponent":
                    stat["attacks"] += 1
                t = e.breakdown.get("opp_threat")
                if t is not None:
                    stat["threat_sum"] += t
                    stat["threat_reads"] += 1
                    if t >= 0.4:
                        stat["hi_shots"] += 1
                        if e.action == "opponent":
                            stat["hi_attacks"] += 1
                    if t >= 0.15:
                        stat["mid_shots"] = stat.get("mid_shots", 0) + 1
                        if e.action == "opponent":
                            stat["mid_attacks"] = stat.get("mid_attacks", 0) + 1
            elif e.type == "item_use":
                players[e.player_name]["items"] += 1

    print(f"对局数 ≈ {n_matches} · 平均回合数 {turns_total / n_matches:.1f}")
    print(f"{'选手':<10}{'攻击率':>8}{'道具/回合':>10}{'平均威胁':>9}{'中威胁占比':>11}{'中威胁攻击率':>12}")
    for name, s in players.items():
        atk = s["attacks"] / s["shots"] if s["shots"] else 0
        itp = s["items"] / s["shots"] if s["shots"] else 0
        thr = s["threat_sum"] / s["threat_reads"] if s["threat_reads"] else 0
        mid = s.get("mid_shots", 0)
        mid_ratio = mid / s["threat_reads"] if s["threat_reads"] else 0
        mid_atk = s.get("mid_attacks", 0) / mid if mid else 0
        print(f"{name:<10}{atk:>8.3f}{itp:>10.3f}{thr:>9.3f}"
              f"{mid_ratio:>11.3f}{mid_atk:>12.3f}")


if __name__ == "__main__":
    main()
