from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, WebSocket

from engine.factory import create_game
from server.schemas import CreateGameRequest, HumanActionRequest
from server.state import add_game, get_game

router = APIRouter(prefix="/api/game", tags=["game"])

ws_game_connections: dict[str, list[tuple[WebSocket, str | None]]] = {}


async def broadcast_game_update(game_id: str, state: dict) -> None:
    """向所有订阅连接推送状态。每条连接按自身 viewer 重新序列化（信息公平）。"""
    if game_id not in ws_game_connections:
        return
    game = get_game(game_id)
    for ws, viewer in ws_game_connections[game_id][:]:
        try:
            payload = game.get_state(viewer=viewer) if game is not None else state
            await ws.send_text(json.dumps({"type": "game_update", "state": payload}))
        except Exception:
            ws_game_connections[game_id].remove((ws, viewer))


@router.post("/create")
async def create_new_game(req: CreateGameRequest):
    game = create_game(
        player1_template=req.player1,
        player2_template=req.player2,
        human_player=req.human_player,
        total_slots=req.total_slots,
        live_bullets=req.live_bullets,
        mode=req.mode,
        max_charges=req.max_charges,
        item_set=req.item_set,
    )
    add_game(game)
    return {"game_id": game.id, "state": game.get_state()}


@router.get("/{game_id}")
async def get_game_state(game_id: str, viewer: str | None = None):
    """查询对局状态。viewer 声明视角（私有情报过滤）；缺省为观战视角。"""
    game = get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game.get_state(viewer=viewer)


@router.post("/{game_id}/action")
async def human_action(game_id: str, req: HumanActionRequest):
    game = get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if req.item_id is not None:
        try:
            state = game.human_use_item(req.item_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        state = game.human_action(req.choice)
    await broadcast_game_update(game_id, state)
    return state


@router.post("/{game_id}/auto-step")
async def auto_step(game_id: str):
    game = get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    state = game.ai_step()
    await broadcast_game_update(game_id, state)
    return state


@router.post("/{game_id}/auto-play")
async def auto_play(game_id: str):
    game = get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    state = game.auto_play_to_end()
    await broadcast_game_update(game_id, state)
    return state