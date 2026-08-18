# 🔫 AI 俄罗斯轮盘大逃杀

回合制心理博弈模拟器：六名性格各异的 AI 选手（Claude / GPT / Kimi / Gemini / GLM / DeepSeek）围绕一把随机装填的轮盘手枪对决，每回合在"**自击**"与"**击敌**"之间决策，依据性格参数与实时心态动态博弈。

纯 Python 引擎 + FastAPI 服务 + 原生前端，单容器即可跑起来。

## 界面模式

| 模式 | 说明 |
|------|------|
| 🧑‍💻 人类 vs AI | 你亲自上场，与 AI 一决高下（私有情报信息公平） |
| 🤖 AI vs AI 观战 | 观看任意两名 AI 的智力对决，实时决策明细 |
| 🏆 AI 锦标赛 | 六人循环赛（15 场），积分榜实时更新 |
| 🏟️ 模型竞技场 | AI 1v1 决斗轮盘：双方各持一把随机装填的轮盘。赛前可查看选手性格参数与历史胜率，选边下注按赔率赢积分（初始 1,000，本地留存） |

## 快速开始（本地）

```bash
# 需要 Python 3.10+
pip install -r requirements.txt
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 <http://localhost:8000> 即可。

运行测试（190 个，含决斗轮盘与服务层测试）：

```bash
python -m unittest discover -s tests
```

## 部署到自己的服务器

以下以 Linux 服务器（Ubuntu/Debian 为例）为准，两种方式任选其一。

### 方式一：Docker（推荐）

服务器装有 Docker 与 Docker Compose 时，一条命令启动：

```bash
cd game-trigger-main
docker compose up -d --build
```

- 服务监听容器内 8000 端口，默认映射到宿主机 `8000`
- `restart: unless-stopped` 保证服务器重启后自动拉起
- 查看日志：`docker compose logs -f`；停止：`docker compose down`

### 方式二：裸机 + systemd 常驻

**1. 安装依赖**（建议专用用户与虚拟环境）：

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
sudo useradd -m -s /bin/bash roulette || true
sudo -iu roulette git clone <你的仓库地址> ~/game-trigger-main
cd ~/game-trigger-main
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**2. 创建 systemd 服务** `/etc/systemd/system/roulette.service`：

```ini
[Unit]
Description=AI Roulette Arena
After=network.target

[Service]
User=roulette
WorkingDirectory=/home/roulette/game-trigger-main
ExecStart=/home/roulette/game-trigger-main/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**3. 启动并设为开机自启**：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now roulette
sudo systemctl status roulette      # 确认 active (running)
```

### 放行端口与访问

```bash
# 云服务器安全组放行 8000/tcp 后，或：
sudo ufw allow 8000/tcp
curl http://localhost:8000/health   # {"status":"ok"} 即部署成功
```

浏览器访问 `http://<服务器IP>:8000`。

### 可选：Caddy 自动 HTTPS（Docker，推荐）

仓库已内置 `Caddyfile` 与双服务版 `docker-compose.yml`（app + caddy）。Caddy 会自动签发并续期 Let's Encrypt 证书，无需手动管证书：

1. **域名解析**：把你的域名（如 `trigger.game.luxlife.top`）A 记录指向服务器 IP。
2. **放行端口**：云安全组与服务器防火墙放行 `80/tcp` 与 `443/tcp`：
   ```bash
   sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
   ```
3. **改 Caddyfile**：把 `Caddyfile` 里的域名换成你自己的（仓库默认即 `trigger.game.luxlife.top`）。
4. **一键启动**：
   ```bash
   docker compose up -d --build
   ```
   首次启动约 20–60 秒内 Caddy 自动申请证书。访问 `https://<你的域名>` 即可。
   - 查看证书签发日志：`docker compose logs -f caddy`
   - WebSocket 观战链路由 Caddy 默认透传，无需额外配置

### 可选：Nginx 反向代理（域名 + HTTPS）

```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;    # WebSocket 必需
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

配置后用 `certbot --nginx -d your.domain.com` 一键上 HTTPS。

> 提示：对局会话保存在内存中（TTL 1 小时自动清理），单实例部署即可；如需多实例，需自行引入共享存储。

## 玩法速览

- **经典轮盘**：六槽左轮，1 实 5 空，随机装填；自击空弹连庄，自击实弹出局，击敌实弹获胜
- **决斗轮盘**：双方**各持一把**独立装填的左轮，用自己的枪选自击/击敌；弹巢独立打空独立重装（模型竞技场默认）
- **恶魔轮盘**：霰弹枪 2–8 发随机装填、实/空配比公开，电荷制生命（默认 3 点），可开 9 种道具（放大镜/啤酒/香烟/手锯/手铐/反转器/电话/过期药/肾上腺素）
- **AI 心理**：每位选手由 R（攻击阈值）/S（惯性）/C（冷静）/L（波动）四个性格参数驱动，带实时心态 M 与 L2 对手信念建模

完整规则、决策数学、选手参数与 10 万届基准数据见 **[docs/DESIGN.md](docs/DESIGN.md)**。

## 开发者命令

```bash
python -m engine.simulate --mode buckshot --items full    # 10 万届基准模拟（固定种子可复现）
python -m engine.evolve --smoke                           # CMA-ES 人格进化（冒烟）
python benchmarks\verify_personality.py                   # 人格行为签名统计
```

## 项目结构

```
game-trigger-main/
├── engine/          # 纯 Python 游戏引擎（模式/道具/决策/对手建模/进化）
├── server/          # FastAPI 服务层（REST + WebSocket，信息公平）
├── static/          # 原生前端（模式选择/对战观战/竞技场）
├── tests/           # 单元测试（176 个）
├── benchmarks/      # 基准数据与进化参数存档
├── docs/DESIGN.md   # 完整设计文档
├── Dockerfile / docker-compose.yml
└── requirements.txt
```
