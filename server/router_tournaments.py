from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, WebSocket

from engine.factory import create_tournament
from server.schemas import CreateTournamentRequest
from server.state import add_tournament, get_tournament

router = APIRouter(prefix="/api/tournament", tags=["tournament"])

ws_tournament_connections: dict[str, list[WebSocket]] = {}


async def broadcast_tournament_update(tournament_id: str, state: dict) -> None:
    if tournament_id in ws_tournament_connections:
        data = json.dumps({"type": "tournament_update", "state": state})
        for ws in ws_tournament_connections[tournament_id][:]:
            try:
                await ws.send_text(data)
            except Exception:
                ws_tournament_connections[tournament_id].remove(ws)


@router.post("/create")
async def create_new_tournament(req: CreateTournamentRequest):
    runner = create_tournament(
        player_count=req.player_count,
        total_slots=req.total_slots,
        live_bullets=req.live_bullets,
        seed=req.seed,
        mode=req.mode,
        max_charges=req.max_charges,
        item_set=req.item_set,
    )
    add_tournament(runner)
    return {"tournament_id": runner.id, "state": runner.get_state()}


@router.get("/{tournament_id}")
async def get_tournament_state(tournament_id: str):
    runner = get_tournament(tournament_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return runner.get_state()


@router.post("/{tournament_id}/step")
async def tournament_step(tournament_id: str):
    runner = get_tournament(tournament_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Tournament not found")
    state = runner.step()
    await broadcast_tournament_update(tournament_id, state)
    return state


@router.post("/{tournament_id}/run-all")
async def tournament_run_all(tournament_id: str):
    runner = get_tournament(tournament_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Tournament not found")
    state = runner.run_all()
    await broadcast_tournament_update(tournament_id, state)
    return state