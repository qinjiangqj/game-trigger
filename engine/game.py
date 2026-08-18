from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import Optional

from .config import (DEFAULT_TOTAL_SLOTS, DEFAULT_LIVE_BULLETS, DEFAULT_MODE,
                     DEFAULT_MAX_CHARGES, DEFAULT_ITEM_SET, ITEM_SLOT_CAP,
                     VALID_ITEM_SETS)
from .decision import (make_decision, make_utility_decision, next_item_action,
                       fuse_p_live)
from .items import ITEM_REGISTRY, check_usable, grant_items, resolve_item
from .models import AIPlayer, RouletteGun, Shotgun
from .theory import compute_threat


@dataclass
class GameEvent:
    """对局事件。type: decision/fire/result/item_use/peek/damage/game_over"""
    type: str
    player_name: str
    player_character: str
    action: Optional[str] = None  # "self" or "opponent"
    target_name: Optional[str] = None
    is_live: Optional[bool] = None  # True=实弹, False=空枪
    breakdown: Optional[dict] = None
    message: Optional[str] = None
    winner_name: Optional[str] = None
    item_id: Optional[str] = None       # item_use/peek 事件的道具 id
    damage: Optional[int] = None        # fire 事件的伤害值（含手锯 ×2）
    private_to: Optional[str] = None    # 私有事件接收者

    def to_dict(self, viewer: Optional[str] = None, reveal: bool = False) -> dict:
        """按 viewer 序列化：peek 类私有事件对非接收者隐藏结果（信息公平）。

        reveal=True（终局复盘）：跳过遮蔽，向所有视角揭示情报内容。
        """
        d = {"type": self.type, "player_name": self.player_name,
             "player_character": self.player_character, "action": self.action,
             "target_name": self.target_name, "is_live": self.is_live,
             "message": self.message, "winner_name": self.winner_name,
             "item_id": self.item_id, "damage": self.damage,
             "private_to": self.private_to}
        if self.breakdown is not None:
            d["breakdown"] = self.breakdown
        if self.type == "peek" and self.private_to is not None \
                and self.private_to != viewer and not reveal:
            d["message"] = f"🔒 {self.player_name} 获得了一条私密情报（对你不可见）"
            d["is_live"] = None
            d["masked"] = True
        return d


_AUTO_VIEWER = object()   # get_state 缺省哨兵：自动取人类玩家视角


class GameSession:
    """两人对局。回合制：当前玩家决策 → 射击 → 根据结果判定蝉联/交换/胜负

    mode="classic"   经典俄罗斯轮盘：左轮 1 实弹，一枪定生死，自击空枪蝉联
    mode="buckshot"  恶魔轮盘：霰弹枪 2-8 发随机配比（数量公开），电荷生命制，
                     自击空枪蝉联；自击实弹扣 1 电荷并移交回合；击敌实弹扣敌电荷
    mode="duel"      决斗轮盘：两名玩家各持一把独立随机装填的左轮，行动者用
                     自己的枪射击（自击或击敌），弹巢独立打空独立重装，其余
                     胜负判定与 classic 一致
    """

    def __init__(self, p1: AIPlayer, p2: AIPlayer, total_slots: int = DEFAULT_TOTAL_SLOTS,
                 live_bullets: int = DEFAULT_LIVE_BULLETS, game_id: Optional[str] = None,
                 mode: str = DEFAULT_MODE, max_charges: int = DEFAULT_MAX_CHARGES,
                 item_set: str = DEFAULT_ITEM_SET,
                 rng: Optional[random.Random] = None):
        self.id = game_id or uuid.uuid4().hex[:8]
        self.p1 = p1
        self.p2 = p2
        self.mode = mode
        if mode == "buckshot" and item_set not in VALID_ITEM_SETS:
            raise ValueError(f"Unknown item set: {item_set}")
        self.item_set = "none" if mode != "buckshot" else item_set
        self._rng = rng if rng is not None else random

        self._guns: Optional[dict[str, RouletteGun]] = None   # duel：按玩家名索引
        self._shared_gun: Optional[RouletteGun | Shotgun] = None
        if mode == "buckshot":
            for p in (p1, p2):
                if p.max_charges is None:
                    p.max_charges = max_charges
            self._shared_gun = Shotgun(rng=self._rng)
        elif mode == "classic":
            self._shared_gun = RouletteGun(total_slots, live_bullets, rng=self._rng)
        elif mode == "duel":
            self._guns = {
                p1.name: RouletteGun(total_slots, live_bullets, rng=self._rng),
                p2.name: RouletteGun(total_slots, live_bullets, rng=self._rng),
            }
        else:
            raise ValueError(f"Unknown mode: {mode}")

        self.current = p1
        self.opponent = p2
        self.events: list[GameEvent] = []
        self.is_over = False
        self.winner: Optional[AIPlayer] = None
        self.turn_count = 0

        p1.prepare_for_match(p2.name)
        p2.prepare_for_match(p1.name)
        if self.item_set != "none":
            grant_items((p1, p2), self.item_set, rng=self._rng)

    @property
    def gun(self) -> "RouletteGun | Shotgun":
        """当前行动者将要击发的枪。duel 模式返回行动者自己的枪，其余模式为共享枪。"""
        if self._guns is not None:
            return self._guns[self.current.name]
        return self._shared_gun

    def get_state(self, viewer=_AUTO_VIEWER) -> dict:
        """按 viewer 序列化对局状态（信息公平）。

        - 缺省（哨兵）：自动取人类玩家视角；纯 AI 对局为观战视角
        - viewer 指名玩家：仅该玩家可见自己的私有情报与 known_shells
        - viewer=None：观战视角，所有私有情报打码
        - 终局（is_over）：私有情报全部揭示（复盘视角）
        """
        if viewer is _AUTO_VIEWER:
            viewer = self._viewer_name()

        def _player_state(p: AIPlayer) -> dict:
            d = p.to_dict()
            if viewer is not None and p.name != viewer:
                d["known_shells"] = {}   # 对手私有信息集不可见
            return d

        state = {
            "id": self.id,
            "mode": self.mode,
            "item_set": self.item_set,
            "p1": _player_state(self.p1),
            "p2": _player_state(self.p2),
            "gun": self.gun.to_dict(),
            "current_player": self.current.name,
            "opponent_player": self.opponent.name,
            "is_over": self.is_over,
            "winner": self.winner.name if self.winner else None,
            "turn_count": self.turn_count,
            "needs_human_input": self.current.is_human and not self.is_over,
            "events": [e.to_dict(viewer=viewer, reveal=self.is_over)
                       for e in self.events],
        }
        if self._guns is not None:
            # duel：双方弹巢状态均为公开信息（数量公开、顺序保密）
            state["guns"] = {name: g.to_dict() for name, g in self._guns.items()}
        return state

    def _viewer_name(self) -> Optional[str]:
        """人类玩家的默认视角（无人类则为观战视角 None）。"""
        if self.p1.is_human:
            return self.p1.name
        if self.p2.is_human:
            return self.p2.name
        return None

    def ai_step(self) -> dict:
        """AI 自动决策一步。若当前玩家是人类则直接返回（需等待 human_action）。"""
        if self.is_over:
            return self.get_state()
        if self.current.is_human:
            return self.get_state()
        self._do_step()
        return self.get_state()

    def human_action(self, choice: str) -> dict:
        if self.is_over or not self.current.is_human:
            return self.get_state()
        if choice not in ("self", "opponent"):
            raise ValueError("choice must be 'self' or 'opponent'")

        self.current.last_choice = choice
        self.events.append(GameEvent(
            type="decision",
            player_name=self.current.name,
            player_character=self.current.character,
            action=choice,
            target_name=self.opponent.name if choice == "opponent" else self.current.name,
            message=f"你选择【{'射击对方' if choice == 'opponent' else '射击自己'}】",
        ))
        self._execute_shot(choice)
        return self.get_state()

    def auto_play_to_end(self) -> dict:
        """自动完成剩余回合（含人类玩家，不等待交互）。"""
        while not self.is_over:
            self._do_step()
        return self.get_state()

    def _do_step(self) -> None:
        """执行一轮：AI 道具阶段 → 射击决策 → 开火 → 结果判定。无视 is_human 标记。"""
        if self.mode == "buckshot":
            if self.item_set != "none":
                self._item_phase_ai()
            if not self.is_over:
                p_live = fuse_p_live(self.gun, self.current)
                dmg = 2 if self.current.sawed else 1
                opp_threat = compute_threat(self.current.opp_model,
                                            self.opponent, self.current.charges)
                choice, breakdown = make_utility_decision(
                    self.current, p_live, self.current.charges, self.opponent.charges,
                    dmg=dmg, rng=self._rng, opp_threat=opp_threat)
        else:
            choice, breakdown = make_decision(
                self.current, self.gun.get_p0(), self.opponent.name, rng=self._rng)

        if not self.is_over:
            self.events.append(GameEvent(
                type="decision",
                player_name=self.current.name,
                player_character=self.current.character,
                action=choice,
                target_name=self.opponent.name if choice == "opponent" else self.current.name,
                breakdown=breakdown.to_dict(),
                message=f"{self.current.name} 选择【{'射击对方' if choice == 'opponent' else '射击自己'}】",
            ))
            self._execute_shot(choice)

    # ==================== 道具阶段（Phase 2） ====================

    def _item_phase_ai(self) -> None:
        """AI 道具阶段：循环启发式直到无道具可用。啤酒退光弹仓时立即重装。"""
        if self.item_set == "none":
            return
        attempted: set[str] = set()
        for _ in range(ITEM_SLOT_CAP):
            item_id = next_item_action(self.current, self.gun, self.opponent,
                                       rng=self._rng, attempted=attempted)
            if item_id is None:
                break
            self._use_item(self.current, item_id)
            if self.is_over:
                return
            if self.gun.is_empty:
                self._check_reload()
                attempted = set()   # 新弹仓：道具价值重估，允许重新掷骰
        if self.gun.is_empty and not self.is_over:
            self._check_reload()

    def _use_item(self, player: AIPlayer, item_id: str) -> Optional[str]:
        """校验并使用道具，发射事件。返回错误原因（None=成功）。不消耗回合。"""
        opp = self.opponent if player is self.current else self.current
        reason = check_usable(item_id, player, self.gun, opp)
        if reason is not None:
            return reason
        if player is not self.current:
            return "不是该玩家的回合"

        outcome = resolve_item(item_id, self.gun, player, opp, rng=self._rng)
        self._emit_item_events(player, opp, item_id, outcome)

        # 过期药（含被肾上腺素偷用）可能直接致死
        if (not self.is_over and player.charges is not None
                and player.charges <= 0):
            self.events.append(GameEvent(
                type="damage", player_name=player.name,
                player_character=player.character,
                target_name=player.name, damage=1,
                message=f"💀 {player.name} 电荷归零，倒地出局！",
            ))
            player.update_mindset("loss", opponent=opp)
            opp.update_mindset("win", opponent=player)
            self._end_game(opp)
        return None

    def _emit_item_events(self, player: AIPlayer, opp: AIPlayer,
                          item_id: str, outcome: dict) -> None:
        """按道具结算结果发射事件（含私有事件）。肾上腺素嵌套复用本函数。"""
        item_def = ITEM_REGISTRY[item_id]

        if item_id == "magnifier":
            is_live = outcome["peek_live"]
            self.events.append(GameEvent(
                type="item_use", player_name=player.name,
                player_character=player.character, item_id=item_id,
                private_to=player.name,
                message=f"{item_def.icon} {player.name} 使用【{item_def.name}】查看当前弹"))
            self.events.append(GameEvent(
                type="peek", player_name=player.name,
                player_character=player.character, item_id=item_id,
                is_live=is_live, private_to=player.name,
                message=f"🔒 查看结果：当前弹为{'🔴 实弹' if is_live else '🔵 空弹'}"))
        elif item_id == "burner_phone":
            offset = outcome["phone_offset"]
            is_live = outcome["phone_live"]
            self.events.append(GameEvent(
                type="item_use", player_name=player.name,
                player_character=player.character, item_id=item_id,
                private_to=player.name,
                message=f"{item_def.icon} {player.name} 使用【{item_def.name}】查询未来弹"))
            self.events.append(GameEvent(
                type="peek", player_name=player.name,
                player_character=player.character, item_id=item_id,
                is_live=is_live, private_to=player.name,
                message=f"🔒 电话情报：第 {offset + 1} 发是{'🔴 实弹' if is_live else '🔵 空弹'}"))
        elif item_id == "inverter":
            new_live = outcome["inverted_live"]
            self.events.append(GameEvent(
                type="item_use", player_name=player.name,
                player_character=player.character, item_id=item_id,
                private_to=player.name,
                message=f"{item_def.icon} {player.name} 使用【{item_def.name}】反转当前弹（公开计数已更新）"))
            self.events.append(GameEvent(
                type="peek", player_name=player.name,
                player_character=player.character, item_id=item_id,
                is_live=new_live, private_to=player.name,
                message=f"🔒 反转结果：当前弹变为{'🔴 实弹' if new_live else '🔵 空弹'}"))
        elif item_id == "expired_medicine":
            healed = outcome["healed"]
            delta = outcome["delta"]
            if healed:
                self.events.append(GameEvent(
                    type="item_use", player_name=player.name,
                    player_character=player.character, item_id=item_id,
                    message=f"{item_def.icon} {player.name} 吞下【{item_def.name}】药效生效 +{delta} 电荷"
                            f"（{player.charges}/{player.max_charges}）"))
            else:
                self.events.append(GameEvent(
                    type="item_use", player_name=player.name,
                    player_character=player.character, item_id=item_id,
                    damage=1,
                    message=f"{item_def.icon} {player.name} 吞下【{item_def.name}】药已变质 {delta} 电荷"
                            f"（{player.charges}/{player.max_charges}）"))
        elif item_id == "adrenaline":
            stolen = outcome.get("stolen")
            if stolen is None:
                self.events.append(GameEvent(
                    type="item_use", player_name=player.name,
                    player_character=player.character, item_id=item_id,
                    message=f"{item_def.icon} {player.name} 使用【{item_def.name}】但没有可偷的道具"))
            else:
                stolen_def = ITEM_REGISTRY[stolen]
                self.events.append(GameEvent(
                    type="item_use", player_name=player.name,
                    player_character=player.character, item_id=item_id,
                    target_name=opp.name,
                    message=f"{item_def.icon} {player.name} 使用【{item_def.name}】"
                            f"偷取 {opp.name} 的【{stolen_def.name}】并立即使用！"))
                self._emit_item_events(player, opp, stolen,
                                       outcome["stolen_result"])
        elif item_id == "beer":
            ejected_live = outcome["ejected_live"]
            live, blank = self.gun.get_counts()
            self.events.append(GameEvent(
                type="item_use", player_name=player.name,
                player_character=player.character, item_id=item_id,
                is_live=ejected_live,
                message=f"{item_def.icon} {player.name} 使用【{item_def.name}】退弹——"
                        f"退出{'🔴 实弹' if ejected_live else '🔵 空弹'}，剩余 实×{live} / 空×{blank}"))
        elif item_id == "cigarette":
            healed = outcome["healed"]
            self.events.append(GameEvent(
                type="item_use", player_name=player.name,
                player_character=player.character, item_id=item_id,
                message=f"{item_def.icon} {player.name} 使用【{item_def.name}】回复 {healed} 电荷"
                        f"（{player.charges}/{player.max_charges}）"))
        elif item_id == "handsaw":
            self.events.append(GameEvent(
                type="item_use", player_name=player.name,
                player_character=player.character, item_id=item_id,
                message=f"{item_def.icon} {player.name} 使用【{item_def.name}】——下次实弹伤害 ×2！"))
        elif item_id == "handcuff":
            self.events.append(GameEvent(
                type="item_use", player_name=player.name,
                player_character=player.character, item_id=item_id,
                target_name=opp.name,
                message=f"{item_def.icon} {player.name} 使用【{item_def.name}】铐住 {opp.name}——"
                        f"{opp.name} 下回合被跳过！"))

    def human_use_item(self, item_id: str) -> dict:
        """人类玩家使用道具。道具不消耗回合，使用后仍需射击。"""
        if self.is_over:
            return self.get_state()
        if not self.current.is_human:
            raise ValueError("当前不是人类玩家的回合")
        err = self._use_item(self.current, item_id)
        if err is not None:
            raise ValueError(err)
        if self.gun.is_empty:
            self._check_reload()
        return self.get_state()

    def _execute_shot(self, choice: str) -> None:
        if self.mode == "buckshot":
            self._execute_shot_buckshot(choice)
        else:
            self._execute_shot_classic(choice)

    def _execute_shot_classic(self, choice: str) -> None:
        is_live = self.gun.shoot()
        self.turn_count += 1

        if choice == "self":
            if is_live:
                self.events.append(GameEvent(
                    type="fire",
                    player_name=self.current.name,
                    player_character=self.current.character,
                    action="self",
                    is_live=True,
                    message=f"💥 实弹！{self.current.name} 出局！",
                ))
                self.current.is_alive = False
                self.current.update_mindset("loss", opponent=self.opponent)
                self.opponent.update_mindset("win", opponent=self.current)
                self._end_game(self.opponent)
            else:
                self.events.append(GameEvent(
                    type="fire",
                    player_name=self.current.name,
                    player_character=self.current.character,
                    action="self",
                    is_live=False,
                    message=f"🍃 空枪！{self.current.name} 蝉联继续！",
                ))
                self._check_reload()
        else:
            if is_live:
                self.events.append(GameEvent(
                    type="fire",
                    player_name=self.current.name,
                    player_character=self.current.character,
                    action="opponent",
                    target_name=self.opponent.name,
                    is_live=True,
                    message=f"🎯 实弹！{self.current.name} 击杀 {self.opponent.name}！",
                ))
                self.opponent.is_alive = False
                self.current.update_mindset("win", opponent=self.opponent)
                self.opponent.update_mindset("loss", opponent=self.current)
                self._end_game(self.current)
            else:
                self.events.append(GameEvent(
                    type="fire",
                    player_name=self.current.name,
                    player_character=self.current.character,
                    action="opponent",
                    target_name=self.opponent.name,
                    is_live=False,
                    message=f"🍃 空枪！{self.opponent.name} 躲过一劫，轮到对方！",
                ))
                self._check_reload()
                self.current, self.opponent = self.opponent, self.current

    def _execute_shot_buckshot(self, choice: str) -> None:
        public_p_before = self.gun.get_p0()   # 射击前公开配比（行为反推基准）
        had_peek = self.opponent.opp_model.peek_current >= 0.99
        is_live = self.gun.shoot()
        # —— 信念模型观察（Phase 4 L2+）——
        # 指针前移推进双方模型（情报消费+电话到期），随后行为证据写入不被衰减
        self.current.opp_model.on_advance()
        self.opponent.opp_model.on_advance()
        self.opponent.opp_model.observe_shot(choice, is_live, public_p_before,
                                             had_peek=had_peek)
        dmg = 2 if self.current.sawed else 1
        saw_tag = "（手锯 ×2）" if self.current.sawed else ""
        self.turn_count += 1
        # 手锯增益在任意一次射击后清除；双方私有信息集随指针前移重映射
        self.current.sawed = False
        self.current.advance_known()
        self.opponent.advance_known()
        shooter, target = self.current, self.opponent

        if choice == "self":
            if is_live:
                dead = shooter.take_damage(dmg)
                if dead:
                    self.events.append(GameEvent(
                        type="fire", player_name=shooter.name,
                        player_character=shooter.character, action="self", is_live=True,
                        damage=dmg,
                        message=f"💥 实弹{saw_tag}！{shooter.name} 自击倒地（电荷归零）！",
                    ))
                    shooter.update_mindset("loss", opponent=target)
                    target.update_mindset("win", opponent=shooter)
                    self._end_game(target)
                    return
                self.events.append(GameEvent(
                    type="fire", player_name=shooter.name,
                    player_character=shooter.character, action="self", is_live=True,
                    damage=dmg,
                    message=f"💥 实弹{saw_tag}！{shooter.name} 自击中弹，"
                            f"电荷 {shooter.charges + dmg}→{shooter.charges}，回合移交",
                ))
                self._check_reload()
                self._swap_turn()
            else:
                self.events.append(GameEvent(
                    type="fire", player_name=shooter.name,
                    player_character=shooter.character, action="self", is_live=False,
                    message=f"🍃 空弹！{shooter.name} 自击蝉联，继续行动！",
                ))
                self._check_reload()
        else:
            if is_live:
                dead = target.take_damage(dmg)
                if dead:
                    self.events.append(GameEvent(
                        type="fire", player_name=shooter.name,
                        player_character=shooter.character, action="opponent",
                        target_name=target.name, is_live=True, damage=dmg,
                        message=f"🎯 实弹{saw_tag}！{shooter.name} 击倒 {target.name}（电荷归零）！",
                    ))
                    shooter.update_mindset("win", opponent=target)
                    target.update_mindset("loss", opponent=shooter)
                    self._end_game(shooter)
                    return
                self.events.append(GameEvent(
                    type="fire", player_name=shooter.name,
                    player_character=shooter.character, action="opponent",
                    target_name=target.name, is_live=True, damage=dmg,
                    message=f"🎯 实弹{saw_tag}！{target.name} 中弹，"
                            f"电荷 {target.charges + dmg}→{target.charges}，回合移交",
                ))
            else:
                self.events.append(GameEvent(
                    type="fire", player_name=shooter.name,
                    player_character=shooter.character, action="opponent",
                    target_name=target.name, is_live=False,
                    message=f"🍃 空弹！{target.name} 躲过一劫，回合移交",
                ))
            self._check_reload()
            self._swap_turn()

    def _swap_turn(self) -> None:
        """交换回合权。若新行动者被手铐束缚则跳过其回合（清除标记后换回）。"""
        self.current, self.opponent = self.opponent, self.current
        if (self.mode == "buckshot" and not self.is_over
                and self.current.skip_next):
            self.current.skip_next = False
            self.events.append(GameEvent(
                type="result", player_name=self.current.name,
                player_character=self.current.character,
                message=f"🔗 {self.current.name} 被手铐束缚，跳过回合！",
            ))
            self.current, self.opponent = self.opponent, self.current

    def _check_reload(self) -> None:
        if self.gun.pointer >= self.gun.total_slots:
            self.gun.reload()
            if self.mode == "buckshot":
                live, blank = self.gun.get_counts()
                msg = f"🔄 弹仓打空，重新装填：实弹 ×{live} / 空弹 ×{blank}（顺序未知）"
                granted: dict[str, list[str]] = {}
                if self.item_set != "none":
                    granted = grant_items((self.p1, self.p2), self.item_set,
                                          rng=self._rng)
                for p in (self.p1, self.p2):
                    p.known_shells = {}
                    p.last_cuffed = None
                    p.opp_model.reset()   # 新弹仓：信念模型全量重置
                parts = []
                for name, new_items in granted.items():
                    if new_items:
                        icons = " ".join(ITEM_REGISTRY[i].icon for i in new_items)
                        parts.append(f"{name} 获得 {icons}")
                if parts:
                    msg += "；补发道具——" + "，".join(parts)
                self.events.append(GameEvent(
                    type="result",
                    player_name="系统",
                    player_character="",
                    message=msg,
                ))
            else:
                reload_msg = (f"🔄 {self.current.name} 的弹巢打空，自动重新装弹！"
                              if self.mode == "duel"
                              else "🔄 弹巢打空，自动重新装弹！")
                self.events.append(GameEvent(
                    type="result",
                    player_name="系统",
                    player_character="",
                    message=reload_msg,
                ))

    def _end_game(self, winner: AIPlayer) -> None:
        self.is_over = True
        self.winner = winner
        self.events.append(GameEvent(
            type="game_over",
            player_name=winner.name,
            player_character=winner.character,
            winner_name=winner.name,
            message=f"🏆 {winner.name} 获胜！",
        ))


def simulate_match(p1: AIPlayer, p2: AIPlayer, total_slots: int = DEFAULT_TOTAL_SLOTS,
                   live_bullets: int = DEFAULT_LIVE_BULLETS, mode: str = DEFAULT_MODE,
                   max_charges: int = DEFAULT_MAX_CHARGES,
                   item_set: str = DEFAULT_ITEM_SET,
                   rng: Optional[random.Random] = None) -> AIPlayer:
    """轻量版两人对局——不创建 GameEvent，仅返回胜者。用于大规模蒙特卡洛模拟。

    道具阶段与 GameSession 共用同一套启发式（next_item_action）与效果（resolve_item）。
    """
    _rng = rng if rng is not None else random
    if mode == "buckshot":
        # 先定 max_charges 再 prepare（prepare 内会把 charges 重置为上限）
        for p in (p1, p2):
            if p.max_charges is None:
                p.max_charges = max_charges
    p1.prepare_for_match(p2.name)
    p2.prepare_for_match(p1.name)
    items_on = mode == "buckshot" and item_set != "none"

    if mode == "buckshot":
        gun = Shotgun(rng=_rng)
        if items_on:
            grant_items((p1, p2), item_set, rng=_rng)
    elif mode == "duel":
        gun = None
        duel_guns = {p1.name: RouletteGun(total_slots, live_bullets, rng=_rng),
                     p2.name: RouletteGun(total_slots, live_bullets, rng=_rng)}
    else:
        gun = RouletteGun(total_slots, live_bullets, rng=_rng)
    current, opponent = p1, p2

    def _reload() -> None:
        gun.reload()
        for p in (p1, p2):
            p.known_shells = {}
            p.last_cuffed = None
            p.opp_model.reset()
        if items_on:
            grant_items((p1, p2), item_set, rng=_rng)

    def _consume_skip() -> None:
        nonlocal current, opponent
        if current.skip_next:
            current.skip_next = False
            current, opponent = opponent, current

    while True:
        # duel：行动者击发自己的枪；其余模式击发共享枪
        active = duel_guns[current.name] if mode == "duel" else gun
        if mode == "buckshot":
            if items_on:
                attempted: set[str] = set()
                for _ in range(ITEM_SLOT_CAP):
                    item_id = next_item_action(current, gun, opponent, rng=_rng,
                                               attempted=attempted)
                    if item_id is None:
                        break
                    resolve_item(item_id, gun, current, opponent, rng=_rng)
                    if current.charges is not None and current.charges <= 0:
                        # 过期药致死（含被偷用）
                        current.update_mindset("loss", opponent)
                        opponent.update_mindset("win", current)
                        return opponent
                    if gun.is_empty:
                        _reload()
                        attempted = set()
            dmg = 2 if current.sawed else 1
            opp_threat = compute_threat(current.opp_model, opponent, current.charges)
            public_p_before = gun.get_p0()
            had_peek = opponent.opp_model.peek_current >= 0.99
            choice, _ = make_utility_decision(
                current, fuse_p_live(gun, current), current.charges, opponent.charges,
                dmg=dmg, rng=_rng, opp_threat=opp_threat)
        else:
            choice, _ = make_decision(current, active.get_p0(), opponent.name, rng=_rng)

        is_live = active.shoot()
        if mode == "buckshot":
            # 信念模型观察：指针前移推进双方模型，随后行为证据写入（Phase 4 L2+）
            current.opp_model.on_advance()
            opponent.opp_model.on_advance()
            opponent.opp_model.observe_shot(choice, is_live, public_p_before,
                                            had_peek=had_peek)
        sawed = current.sawed
        dmg = 2 if sawed else 1
        current.sawed = False
        current.advance_known()
        opponent.advance_known()

        if mode == "buckshot":
            if choice == "self":
                if is_live:
                    if current.take_damage(dmg):
                        current.update_mindset("loss", opponent)
                        opponent.update_mindset("win", current)
                        return opponent
                    current, opponent = opponent, current  # 自击实弹存活 → 移交
                    _consume_skip()
                # 自击空弹 → 蝉联
            else:
                if is_live:
                    if opponent.take_damage(dmg):
                        current.update_mindset("win", opponent)
                        opponent.update_mindset("loss", current)
                        return current
                current, opponent = opponent, current  # 击敌（无论中否）→ 移交
                _consume_skip()

            if gun.is_empty:
                _reload()
            continue

        # —— 经典 / 决斗模式 ——
        if choice == "self":
            if is_live:
                current.is_alive = False
                current.update_mindset("loss", opponent)
                opponent.update_mindset("win", current)
                return opponent
        else:
            if is_live:
                opponent.is_alive = False
                current.update_mindset("win", opponent)
                opponent.update_mindset("loss", current)
                return current
            current, opponent = opponent, current

        if active.pointer >= active.total_slots:
            active.reload()
