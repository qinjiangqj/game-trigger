from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from engine.config import get_player_templates
from server.router_games import router as game_router, ws_game_connections
from server.router_tournaments import router as tournament_router, ws_tournament_connections
from server.state import cleanup_loop

app = FastAPI(title="AI 俄罗斯轮盘大逃杀")

app.include_router(game_router)
app.include_router(tournament_router)


@app.on_event("startup")
async def startup():
    asyncio.create_task(cleanup_loop())


@app.get("/api/players")
async def list_players():
    templates = get_player_templates()
    return [{"name": t.name, "character": t.character, "R": t.R, "S": t.S, "C": t.C, "L": t.L}
            for t in templates]


# WebSocket 独立路径，不跟随 /api 前缀
@app.websocket("/ws/game/{game_id}")
async def game_websocket(ws: WebSocket, game_id: str, viewer: str | None = None):
    """对局实时推送。viewer 参数声明连接视角，私有情报按视角过滤（信息公平）。"""
    await ws.accept()
    if game_id not in ws_game_connections:
        ws_game_connections[game_id] = []
    conn = (ws, viewer)
    ws_game_connections[game_id].append(conn)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_game_connections[game_id].remove(conn)


@app.websocket("/ws/tournament/{tournament_id}")
async def tournament_websocket(ws: WebSocket, tournament_id: str):
    await ws.accept()
    if tournament_id not in ws_tournament_connections:
        ws_tournament_connections[tournament_id] = []
    ws_tournament_connections[tournament_id].append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_tournament_connections[tournament_id].remove(ws)


static_dir = Path(__file__).parent.parent / "static"


@app.get("/")
async def index():
    if not static_dir.exists():
        return {"message": "AI 俄罗斯轮盘大逃杀 API", "docs": "/docs"}
    return FileResponse(str(static_dir / "index.html"))


if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}