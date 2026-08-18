// ===================== AI 俄罗斯轮盘大逃杀 - 前端应用 =====================
const STATE = {
    mode: null,
    currentMode: "classic",
    currentGameId: null,
    currentTournamentId: null,
    wsGame: null,
    wsTournament: null,
    players: [],
    autoPlayTimer: null,
    isAutoPlaying: false,
    _lastEventCount: 0,
    _prevScoreKey: "",
    humanName: null,       // 人类玩家名（观战模式为 null，用于私有信息过滤）
    arenaPick: { red: null, blue: null },   // 竞技场选边
    points: null,          // 竞技场积分（localStorage 持久化）
    arenaBet: null,        // 进行中的下注 {side, amount, odds, playerName}
    autoSpeedDelay: 800,   // 自动播放步进间隔（ms）
    lastFinalState: null,  // 终局快照（战报数据源）
    lastBetResult: null,   // 最近一次下注结算文本（战报引用）
};

// 基准胜率（%）：10 万届循环赛，benchmarks/benchmark-20260817.md + 决斗轮盘 20260818
const BENCHMARK_WINRATES = {
    classic: { Kimi: 53.1, GPT: 52.9, Claude: 51.2, GLM: 50.4, Gemini: 49.1, DeepSeek: 43.2 },
    duel:    { GPT: 52.4, Kimi: 52.1, GLM: 51.0, Claude: 50.3, Gemini: 49.5, DeepSeek: 44.8 },
    buckshot_none:     { GPT: 51.0, Kimi: 50.9, Claude: 50.8, Gemini: 50.3, GLM: 49.1, DeepSeek: 47.9 },
    buckshot_standard: { GPT: 51.3, Claude: 50.6, GLM: 50.0, Kimi: 49.4, DeepSeek: 49.4, Gemini: 49.3 },
    buckshot_full:     { GPT: 50.6, GLM: 50.5, Claude: 49.9, Gemini: 49.7, DeepSeek: 49.7, Kimi: 49.7 },
};

// 性格参数元数据：标签 + 条形图满格值（与 engine/config.py 模板量级对应）
const PARAM_META = [
    { key: "R", label: "攻击", max: 0.4, tip: "R 攻击阈值：实弹概率超过该值倾向击敌，越高越像赌徒" },
    { key: "S", label: "惯性", max: 0.7, tip: "S 策略惯性：越爱重复上一次的选择" },
    { key: "C", label: "冷静", max: 0.8, tip: "C 冷静系数：越高越不受心态波动影响" },
    { key: "L", label: "波动", max: 0.2, tip: "L 随机波动：决策噪音幅度，越高越不可测" },
];

const ARENA_INITIAL_POINTS = 1000;
const ARENA_POINTS_KEY = "arena_points";

// 战报开场警句（每次终局随机抽取）
const REPORT_QUOTES = [
    // — 命运与扳机 —
    "命运从来不转轮盘。命运只扣扳机。",
    "扳机不问身份，只问谁的手指还留在上面。",
    "命运给的从来不是子弹，而是扣下去的那一秒。",
    "你以为你在选择——其实子弹早就选好了你。",
    "命运不掷骰子。它只装弹。",
    // — 概率与计算 —
    "概率从不怜悯任何人——它只是计算。",
    "子弹不认识名字，只认识概率。",
    "六分之一的死亡，对那个死去的人就是百分之百。",
    "数学很公平：它公平地杀死每一个人。",
    "空弹不是仁慈，只是概率还没轮到你。",
    "统计学会告诉你谁该死，但不会告诉你为什么是你。",
    // — 轮盘与弹巢 —
    "空枪是运气，实弹是宿命。",
    "转轮停在何处无关紧要，要紧的是你敢不敢扣。",
    "弹巢转一圈，所有人都是过客——只有实弹留到最后。",
    "枪里那颗实弹，一直在等一个名字。",
    "装弹的人早就写好了结局，扣扳机的人只是替它念出来。",
    "转轮不仁。它只是转。",
    // — 恐惧与间隙 —
    "恐惧不是那发实弹，而是等待它响起的间隙。",
    "每一次扣动扳机，都是与死神的一次握手。",
    "最难听的声音不是枪响——是枪没响之后的那一秒寂静。",
    "勇气不是不怕死，是知道下一发可能是空枪仍然扣下去。",
    "沉默是弹巢在转动时唯一的台词。",
    "实弹响之前，所有人都假装自己会是幸运的那个。",
    // — 赌桌与赊账 —
    "活着离开赌桌的人，不过是暂时被命运赊账。",
    "赌桌上的赢家，只是死神还没来收账的客人。",
    "今晚的胜者，明天的筹码。",
    "离桌不等于离场——命运从不让任何人提前退场。",
    "赢家和输家睡在同一张床上，区别只在于谁先合眼。",
    // — 生死与时间 —
    "活着不过是概率还没归零的那段时间。",
    "死人不掷骰子，他们已经是那颗骰子了。",
    "每一发空枪，都是死神签的暂缓执行书。",
    "时间会磨平一切——除了那发该死的实弹。",
    "你活到现在不是因为运气好，是因为弹巢还在转。",
];

const MODE_LABELS = { classic: "经典轮盘", duel: "决斗轮盘", buckshot: "恶魔轮盘" };

// 道具元数据（与 engine/items.py ITEM_REGISTRY 对应）
const ITEM_META = {
    magnifier:      { name: "放大镜", icon: "🔍", desc: "查看当前弹是实是空（仅自己可见）" },
    beer:           { name: "啤酒",   icon: "🍺", desc: "退掉当前弹，退出的弹型公开" },
    cigarette:      { name: "香烟",   icon: "🚬", desc: "回复 1 电荷（不超上限）" },
    handsaw:        { name: "手锯",   icon: "🪚", desc: "下次实弹伤害 ×2（任意射击后清除）" },
    handcuff:       { name: "手铐",   icon: "🔗", desc: "跳过对方下一回合（不可连续铐同一人）" },
    inverter:       { name: "反转器", icon: "🔄", desc: "当前弹实↔空互换（结果仅自己可见）" },
    burner_phone:   { name: "电话",   icon: "📱", desc: "随机获知一发未来弹的位置与类型" },
    expired_medicine: { name: "过期药", icon: "💊", desc: "五五开：+2 电荷 或 −1 电荷" },
    adrenaline:     { name: "肾上腺素", icon: "💉", desc: "偷取对方一个道具并立即使用" },
};

// ===================== 工具函数 =====================
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function showToast(msg, type = "info") {
    let container = $(".toast-container");
    if (!container) {
        container = document.createElement("div");
        container.className = "toast-container";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// ===================== 动画辅助 =====================
function triggerGunRecoil() {
    const icon = document.querySelector(".gun-icon");
    if (icon) {
        icon.classList.remove("gun-recoil");
        void icon.offsetWidth;
        icon.classList.add("gun-recoil");
    }
}

function triggerChamberFire(isLive) {
    // 决斗模式优先在当前行动方的枪上播放击发特效
    let chambers = $$(".duel-gun.active-gun .chamber-slot");
    if (!chambers.length) chambers = $$(".chamber-slot");
    const currentIdx = chambers.findIndex(c => c.classList.contains("current"));
    if (currentIdx >= 0) {
        const c = chambers[currentIdx];
        c.classList.add(isLive ? "fire-live" : "fire-empty");
        setTimeout(() => { c.classList.remove("fire-live", "fire-empty"); }, 600);
    }
}

function triggerKillFlash() {
    const old = document.querySelector(".arena-kill-flash");
    if (old) old.remove();
    const flash = document.createElement("div");
    flash.className = "arena-kill-flash";
    document.body.appendChild(flash);
    setTimeout(() => flash.remove(), 700);
}

function addButtonRipple(e) {
    const btn = e.currentTarget;
    const ripple = document.createElement("span");
    ripple.className = "ripple-effect";
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
    ripple.style.top = `${e.clientY - rect.top - size / 2}px`;
    btn.appendChild(ripple);
    setTimeout(() => ripple.remove(), 700);
}

// ===================== 初始化 =====================
document.addEventListener("DOMContentLoaded", () => {
    loadPlayers();
    setupTabs();
    // 按钮涟漪
    document.body.addEventListener("click", (e) => {
        if (e.target.closest(".btn") && !e.target.closest(".btn:disabled")) {
            addButtonRipple(e);
        }
    });
    // 键盘快捷键（仅对战视图；输入控件聚焦时忽略）
    document.addEventListener("keydown", onHotkey);
    // ESC 关闭战报
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeBattleReport();
    });
});

// 快捷键：人类模式 1=射自己 2=射对方；观战模式 Space/→=下一步 A=自动播放
function onHotkey(e) {
    if (e.target.matches("input, select, textarea, button")) return;
    if (!document.getElementById("battle-report").classList.contains("hidden")) return;   // 战报打开时不响应
    if (!document.getElementById("game-view").classList.contains("active")) return;
    if (!STATE.currentGameId) return;
    if (!document.getElementById("game-over-modal").classList.contains("hidden")) return;

    const humanVisible = !document.getElementById("human-actions").classList.contains("hidden");
    if (humanVisible && !STATE.isAutoPlaying) {
        const shootBtns = document.querySelectorAll("#human-actions .shoot-action-row .btn");
        if ([...shootBtns].some(b => b.disabled)) return;   // 请求进行中
        if (e.key === "1") humanAction("self");
        else if (e.key === "2") humanAction("opponent");
    } else if (!humanVisible) {
        if (e.key === " " || e.key === "ArrowRight") {
            e.preventDefault();
            if (!STATE.isAutoPlaying) autoStep();
        } else if (e.key.toLowerCase() === "a") {
            autoPlay();
        }
    }
}

async function loadPlayers() {
    try {
        const res = await fetch("/api/players");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        STATE.players = await res.json();
        populatePlayerSelects();
    } catch (e) {
        console.error("加载选手列表失败", e);
        showToast("加载选手列表失败，请检查服务器连接", "error");
    }
}

function populatePlayerSelects() {
    const selects = ["hva-opponent", "ava-p1", "ava-p2"];
    selects.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = "";
        STATE.players.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.name;
            opt.textContent = `${p.name} · ${p.character}`;
            sel.appendChild(opt);
        });
    });
    const avaP2 = document.getElementById("ava-p2");
    if (avaP2 && STATE.players.length > 1) avaP2.selectedIndex = 1;
    // 竞技场面板已打开但选手未就绪时，加载完成后补渲染
    if (STATE.mode === "arena") initArenaGrid();
}

// ===================== Tab 导航 =====================
function setupTabs() {
    $$(".tab").forEach(tab => {
        tab.addEventListener("click", () => {
            $$(".tab").forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            $$(".view").forEach(v => v.classList.remove("active"));
            const el = document.getElementById(tab.dataset.tab);
            if (el) el.classList.add("active");
        });
    });
}

function switchTab(name) {
    const tab = $(`[data-tab="${name}"]`);
    if (tab) tab.click();
}

function showTab(name) { const t = document.getElementById(`tab-${name}`); if (t) t.style.display = ""; }
function hideTab(name) { const t = document.getElementById(`tab-${name}`); if (t) t.style.display = "none"; }

// ===================== 模式选择 =====================
function selectMode(mode) {
    STATE.mode = mode;
    $$(".config-panel").forEach(p => p.classList.add("hidden"));
    $$(".mode-card").forEach(c => c.style.opacity = "0.45");
    const map = { "human-vs-ai": "human-vs-ai-config", "ai-vs-ai": "ai-vs-ai-config", "tournament": "tournament-config", "arena": "arena-config" };
    const panel = document.getElementById(map[mode]);
    if (panel) panel.classList.remove("hidden");
    if (mode === "arena") initArenaGrid();
}

function backToModes(restoreMode) {
    stopAutoPlay();
    STATE.mode = null;
    STATE.currentGameId = null;
    STATE.currentTournamentId = null;
    STATE.humanName = null;
    STATE._lastEventCount = 0;
    STATE._prevScoreKey = "";
    closeAllWS();
    $$(".config-panel").forEach(p => p.classList.add("hidden"));
    $$(".mode-card").forEach(c => c.style.opacity = "1");
    document.getElementById("game-over-modal").classList.add("hidden");
    document.getElementById("tournament-over-modal").classList.add("hidden");
    document.getElementById("battle-report").classList.add("hidden");
    hideTab("game");
    hideTab("tournament");
    switchTab("mode-select");
    document.getElementById("event-log-content").innerHTML = "";
    document.getElementById("turn-indicator").textContent = "";
    if (restoreMode) selectMode(restoreMode);
}

// 竞技场再战：清理对局后直接回到竞技场配置（选边/下注面板保留）
function rematchArena() {
    backToModes("arena");
}

// ===================== WebSocket =====================
function connectWS(type, id) {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    // 对局连接声明 viewer 视角：私有情报按视角过滤（信息公平）
    const suffix = type === "game" && STATE.humanName
        ? `?viewer=${encodeURIComponent(STATE.humanName)}` : "";
    const url = `${protocol}//${location.host}/ws/${type}/${id}${suffix}`;
    const ws = new WebSocket(url);

    ws.onopen = () => { console.log(`WS connected: ${type}/${id}`); };
    ws.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data);
            if (type === "game" && data.type === "game_update") {
                updateGameView(data.state);
                if (!data.state.is_over && !data.state.needs_human_input && STATE.isAutoPlaying) {
                    // 自动播放模式下由定时器驱动，WS 更新仅刷新 UI
                }
            } else if (type === "tournament" && data.type === "tournament_update") {
                updateTournamentView(data.state);
            }
        } catch (e) { console.error("WS message parse error", e); }
    };
    ws.onclose = (evt) => {
        console.log(`WS closed: ${type}/${id} code=${evt.code}`);
        if (type === "game") STATE.wsGame = null;
        else STATE.wsTournament = null;
    };
    ws.onerror = () => { /* 静默处理，onclose 会触发 */ };

    if (type === "game") STATE.wsGame = ws;
    else STATE.wsTournament = ws;
}

function closeAllWS() {
    [STATE.wsGame, STATE.wsTournament].forEach(ws => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    });
    STATE.wsGame = null;
    STATE.wsTournament = null;
}

// ===================== API 封装 =====================
async function apiPost(url, body) {
    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
        const text = await res.text();
        let detail = text;
        try { detail = JSON.parse(text).detail || text; } catch (_) { /* 非 JSON 响应 */ }
        throw new Error(detail || `HTTP ${res.status}`);
    }
    return res.json();
}

// ===================== 模式切换 =====================
function onModeChange(prefix) {
    const mode = document.getElementById(`${prefix}-mode`).value;
    const panel = document.getElementById(`${prefix}-mode`).closest(".config-panel");
    // 弹巢/实弹配置同时适用于 classic 与 duel（各持一把时为每把枪的装填）
    panel.querySelectorAll(".classic-only").forEach(el =>
        el.classList.toggle("hidden", mode !== "classic" && mode !== "duel"));
    panel.querySelectorAll(".buckshot-only").forEach(el => el.classList.toggle("hidden", mode !== "buckshot"));
    if (prefix === "ar") refreshArenaIntel();   // 模式/道具变化影响胜率表与赔率
}

function readModeConfig(prefix) {
    const mode = document.getElementById(`${prefix}-mode`).value;
    const cfg = { mode };
    if (mode === "buckshot") {
        cfg.max_charges = +document.getElementById(`${prefix}-charges`).value;
        cfg.item_set = document.getElementById(`${prefix}-items`).value;
    } else {
        cfg.total_slots = +document.getElementById(`${prefix}-slots`).value;
        cfg.live_bullets = +document.getElementById(`${prefix}-bullets`).value;
    }
    return cfg;
}

// ===================== 模型竞技场 =====================
function initArenaGrid() {
    if (!STATE.players.length) { showToast("选手列表加载中，请稍候", "info"); return; }
    ["red", "blue"].forEach(side => {
        const grid = document.getElementById(`arena-${side}-grid`);
        if (!grid || grid.childElementCount) return;   // 已渲染
        grid.innerHTML = "";
        STATE.players.forEach(p => {
            const card = document.createElement("div");
            card.className = "fighter-card";
            card.dataset.side = side;
            card.dataset.name = p.name;
            card.innerHTML = `<span class="fighter-name">${p.name}</span>
                              <span class="fighter-char">${p.character}</span>`;
            card.addEventListener("click", () => pickFighter(side, p.name));
            grid.appendChild(card);
        });
    });
    // 默认随机配对（未选择时）
    if (!STATE.arenaPick.red || !STATE.arenaPick.blue) arenaRandomPair(true);
    refreshArenaIntel();
}

function pickFighter(side, name) {
    const other = side === "red" ? "blue" : "red";
    if (STATE.arenaPick[other] === name) {
        // 对方正持有该选手：自动换边，避免重复
        STATE.arenaPick[other] = STATE.arenaPick[side];
        showToast("两名选手不能相同，已自动换边", "info");
    }
    STATE.arenaPick[side] = name;
    refreshFighterCards();
    refreshArenaIntel();
}

function refreshFighterCards() {
    ["red", "blue"].forEach(side =>
        $$("#arena-" + side + "-grid .fighter-card").forEach(c =>
            c.classList.toggle("picked", c.dataset.name === STATE.arenaPick[side])));
}

function arenaRandomPair(silent) {
    if (!STATE.players.length) return;
    const pool = [...STATE.players];
    const a = pool.splice(Math.floor(Math.random() * pool.length), 1)[0];
    const b = pool[Math.floor(Math.random() * pool.length)];
    STATE.arenaPick.red = a.name;
    STATE.arenaPick.blue = b.name;
    refreshFighterCards();
    refreshArenaIntel();
    if (!silent) showToast(`随机配对：${a.name} vs ${b.name}`, "info");
}

// —— 下注情报与赔率 ——

function loadPoints() {
    if (STATE.points == null) {
        const saved = parseInt(localStorage.getItem(ARENA_POINTS_KEY), 10);
        STATE.points = Number.isFinite(saved) ? saved : ARENA_INITIAL_POINTS;
    }
    return STATE.points;
}

function savePoints() {
    localStorage.setItem(ARENA_POINTS_KEY, String(STATE.points));
}

function updatePointsUI() {
    const points = loadPoints();
    const el = document.getElementById("arena-points-value");
    const next = points.toLocaleString();
    if (el.textContent !== next && el.dataset.touched) {
        el.classList.remove("points-pulse");
        void el.offsetWidth;   // 重启动画
        el.classList.add("points-pulse");
    }
    el.dataset.touched = "1";
    el.textContent = next;
    document.getElementById("arena-reset-points").classList.toggle("hidden", points >= 10);
}

// 当前配置对应的胜率表键（弹巢/实弹数不影响基准表，按主模式与道具集取）
function getWinrateTable() {
    const mode = document.getElementById("ar-mode").value;
    if (mode !== "buckshot") return BENCHMARK_WINRATES[mode];
    const items = document.getElementById("ar-items").value;
    return BENCHMARK_WINRATES[`buckshot_${items}`] || BENCHMARK_WINRATES.buckshot_standard;
}

function computeOdds() {
    const table = getWinrateTable();
    const wr = table[STATE.arenaPick.red] || 50;
    const wb = table[STATE.arenaPick.blue] || 50;
    const pRed = wr / (wr + wb);   // 双方胜率归一化为对本场的胜出概率
    return {
        red: Math.max(1.01, +(1 / pRed).toFixed(2)),
        blue: Math.max(1.01, +(1 / (1 - pRed)).toFixed(2)),
    };
}

// 渲染选手情报卡（性格参数条 + 历史胜率）并刷新赔率
function refreshArenaIntel() {
    const table = getWinrateTable();
    const odds = computeOdds();
    const intel = STATE.players.length
        ? { [STATE.arenaPick.red]: STATE.players.find(p => p.name === STATE.arenaPick.red),
            [STATE.arenaPick.blue]: STATE.players.find(p => p.name === STATE.arenaPick.blue) }
        : {};
    ["red", "blue"].forEach(side => {
        const el = document.getElementById(`arena-${side}-intel`);
        const name = STATE.arenaPick[side];
        const p = intel[name];
        if (!name || !p) { el.innerHTML = ""; return; }
        const wr = table[name];
        const bars = PARAM_META.map(m => `
            <div class="param-row" title="${m.tip}">
                <span class="param-label">${m.label}</span>
                <span class="param-track"><span class="param-fill" style="width:${Math.min(100, p[m.key] / m.max * 100)}%"></span></span>
                <span class="param-value">${p[m.key].toFixed(2)}</span>
            </div>`).join("");
        el.innerHTML = `
            <div class="intel-head">
                <span class="intel-name">${name}</span>
                <span class="intel-wr">历史胜率 <b>${wr != null ? wr.toFixed(1) + "%" : "--"}</b></span>
                <span class="odds-chip ${side}">赔率 ${odds[side].toFixed(2)}</span>
            </div>
            ${bars}`;
    });
    document.getElementById("odds-red").textContent = odds.red.toFixed(2);
    document.getElementById("odds-blue").textContent = odds.blue.toFixed(2);
    updatePointsUI();
}

function arenaResetPoints() {
    STATE.points = ARENA_INITIAL_POINTS;
    savePoints();
    updatePointsUI();
    showToast(`积分已重置为 ${ARENA_INITIAL_POINTS.toLocaleString()}`, "info");
}

async function startArena(withBet) {
    const { red, blue } = STATE.arenaPick;
    if (!red || !blue) { showToast("请先选择双方选手", "error"); return; }
    if (red === blue) { showToast("两名选手不能相同", "error"); return; }

    STATE.arenaBet = null;
    if (withBet) {
        const sideEl = document.querySelector('input[name="bet-side"]:checked');
        if (!sideEl) { showToast("请先选择下注一方（红/蓝）", "error"); return; }
        const amount = Math.floor(+document.getElementById("bet-amount").value);
        if (!Number.isFinite(amount) || amount < 10) { showToast("下注金额至少 10 积分", "error"); return; }
        if (amount % 10 !== 0) { showToast("下注金额需为 10 的整数倍", "error"); return; }
        if (amount > loadPoints()) { showToast("积分不足，请调低下注金额", "error"); return; }
        const odds = computeOdds();
        const side = sideEl.value;
        STATE.arenaBet = { side, amount, odds: odds[side], playerName: STATE.arenaPick[side] };
        STATE.points -= amount;
        savePoints();
        updatePointsUI();
    }

    const cfg = readModeConfig("ar");
    try {
        const data = await apiPost("/api/game/create", {
            player1: red, player2: blue, ...cfg,
        });
        STATE.currentGameId = data.game_id;
        STATE.humanName = null;      // 观战模式：私有信息对观众屏蔽
        STATE._lastEventCount = 0;
        showTab("game"); switchTab("game-view");
        connectWS("game", data.game_id);
        updateGameView(data.state);
        autoPlay();                  // 竞技场：自动播放观战
    } catch (e) {
        // 创建失败：退回下注
        if (STATE.arenaBet) {
            STATE.points += STATE.arenaBet.amount;
            savePoints(); updatePointsUI();
            STATE.arenaBet = null;
        }
        showToast(`创建比赛失败: ${e.message}`, "error");
    }
}

// 赛果结算：由 showGameOver 调用（仅竞技场且有效下注时）
function settleArenaBet(state) {
    const betEl = document.getElementById("game-over-bet");
    if (!STATE.arenaBet) { betEl.classList.add("hidden"); return; }
    const bet = STATE.arenaBet;
    STATE.arenaBet = null;
    const win = state.winner === bet.playerName;
    if (win) {
        const payout = Math.round(bet.amount * bet.odds);
        STATE.points += payout;
        savePoints(); updatePointsUI();
        betEl.textContent = `🎉 押中 ${bet.playerName}！+${(payout - bet.amount).toLocaleString()} 积分（返还 ${payout.toLocaleString()}，赔率 ${bet.odds.toFixed(2)}）`;
        betEl.className = "bet-result win";
        STATE.lastBetResult = { win: true, text: betEl.textContent };
    } else {
        betEl.textContent = `💸 ${bet.playerName} 落败，输掉 ${bet.amount.toLocaleString()} 积分`;
        betEl.className = "bet-result lose";
        STATE.lastBetResult = { win: false, text: betEl.textContent };
    }
}

// ===================== 创建游戏 =====================
async function startHumanVsAI() {
    const opponent = document.getElementById("hva-opponent").value;
    const cfg = readModeConfig("hva");
    try {
        const data = await apiPost("/api/game/create", {
            player1: "你", player2: opponent, human_player: "你", ...cfg,
        });
        STATE.currentGameId = data.game_id;
        STATE.humanName = "你";
        STATE._lastEventCount = 0;
        showTab("game"); switchTab("game-view");
        connectWS("game", data.game_id);
        updateGameView(data.state);
    } catch (e) {
        showToast(`创建游戏失败: ${e.message}`, "error");
    }
}

async function startAIvsAI() {
    const p1 = document.getElementById("ava-p1").value;
    const p2 = document.getElementById("ava-p2").value;
    const cfg = readModeConfig("ava");
    if (p1 === p2) { showToast("请选择不同的选手", "error"); return; }
    try {
        const data = await apiPost("/api/game/create", {
            player1: p1, player2: p2, ...cfg,
        });
        STATE.currentGameId = data.game_id;
        STATE.humanName = null;      // 观战模式：私有信息对观众屏蔽
        STATE._lastEventCount = 0;
        showTab("game"); switchTab("game-view");
        connectWS("game", data.game_id);
        updateGameView(data.state);
    } catch (e) {
        showToast(`创建游戏失败: ${e.message}`, "error");
    }
}

// ===================== 锦标赛 =====================
async function startTournament() {
    const playerCount = +document.getElementById("trn-players").value;
    const cfg = readModeConfig("trn");
    try {
        const data = await apiPost("/api/tournament/create", {
            player_count: playerCount, ...cfg,
        });
        STATE.currentTournamentId = data.tournament_id;
        showTab("tournament"); switchTab("tournament-view");
        connectWS("tournament", data.tournament_id);
        updateTournamentView(data.state);
    } catch (e) {
        showToast(`创建锦标赛失败: ${e.message}`, "error");
    }
}

// ===================== 游戏视图 =====================
function updateGameView(state) {
    STATE.currentMode = state.mode || "classic";
    updatePlayerCard("1", state.p1, state.current_player === state.p1.name);
    updatePlayerCard("2", state.p2, state.current_player === state.p2.name);
    // 人类视角：只有自己的私有信息集可见（观战模式不显示任何已知弹）
    const viewer = STATE.humanName
        ? (state.p1.name === STATE.humanName ? state.p1 : state.p2)
        : null;
    // 决斗轮盘（duel）：双方各持一把，独立展示；其余模式共用一把
    const hasDuelGuns = !!state.guns;
    document.getElementById("gun-display").classList.toggle("hidden", hasDuelGuns);
    document.getElementById("gun-display-duel").classList.toggle("hidden", !hasDuelGuns);
    if (hasDuelGuns) {
        updateDuelGunDisplay(state, state.is_over);
    } else {
        updateGunDisplay(state.gun, state.is_over, viewer ? viewer.known_shells : null);
    }
    document.getElementById("turn-indicator").textContent = state.turn_count > 0 ? `第 ${state.turn_count} 回合` : "";
    updateEventLog(state.events);
    updateActionBar(state);
    if (state.is_over) showGameOver(state);
}

function updatePlayerCard(side, player, isCurrent) {
    const card = document.getElementById(`player${side}-card`);
    document.getElementById(`p${side}-name`).textContent = player.name;
    document.getElementById(`p${side}-character`).textContent = player.character;

    // 电荷（恶魔轮盘模式）
    const chargeRow = document.getElementById(`p${side}-charge-row`);
    const chargeEl = document.getElementById(`p${side}-charges`);
    if (player.max_charges != null) {
        chargeRow.classList.remove("hidden");
        let pips = "";
        for (let i = 0; i < player.max_charges; i++) {
            pips += `<span class="pip ${i < player.charges ? "pip-on" : "pip-off"}"></span>`;
        }
        chargeEl.innerHTML = pips;
    } else {
        chargeRow.classList.add("hidden");
        chargeEl.innerHTML = "";
    }

    // 道具栏（恶魔轮盘模式；双方道具数量公开）
    const itemRow = document.getElementById(`p${side}-item-row`);
    const itemEl = document.getElementById(`p${side}-items`);
    if (player.max_charges != null) {
        itemRow.classList.remove("hidden");
        itemEl.innerHTML = (player.items || []).length > 0
            ? player.items.map(id => {
                const meta = ITEM_META[id] || { name: id, icon: "❔", desc: "" };
                return `<span class="item-chip" title="${meta.desc}">${meta.icon}</span>`;
            }).join("")
            : `<span class="item-empty">—</span>`;
    } else {
        itemRow.classList.add("hidden");
        itemEl.innerHTML = "";
    }

    // 公开状态徽章：手锯增益 / 手铐束缚
    const statusRow = document.getElementById(`p${side}-status-row`);
    const sawedEl = document.getElementById(`p${side}-sawed`);
    const cuffedEl = document.getElementById(`p${side}-cuffed`);
    const hasStatus = player.sawed || player.skip_next;
    statusRow.classList.toggle("hidden", !hasStatus);
    sawedEl.classList.toggle("hidden", !player.sawed);
    cuffedEl.classList.toggle("hidden", !player.skip_next);

    const mindset = player.M;
    const mindsetEl = document.getElementById(`p${side}-mindset`);
    mindsetEl.textContent = mindset.toFixed(2);
    mindsetEl.className = mindset > 0.05 ? "mindset-positive" : mindset < -0.05 ? "mindset-negative" : "";

    const streakEl = document.getElementById(`p${side}-streak`);
    if (player.win_streak > 0) streakEl.textContent = `胜×${player.win_streak}`;
    else if (player.loss_streak > 0) streakEl.textContent = `败×${player.loss_streak}`;
    else streakEl.textContent = "--";

    const avatar = card.querySelector(".player-avatar");
    avatar.textContent = player.is_human ? "🧑‍💻" : "🤖";

    card.classList.remove("active-turn", "dead", "winner-card");
    document.getElementById(`p${side}-indicator`).classList.add("hidden");

    if (!player.is_alive) card.classList.add("dead");
    else if (isCurrent) {
        card.classList.add("active-turn");
        document.getElementById(`p${side}-indicator`).classList.remove("hidden");
    }
}

// 圆形转轮弹仓：槽位按角度环绕中心，中央轮轴显示剩余弹数
function renderChamber(container, gun, isGameOver, knownShells) {
    container.innerHTML = "";
    const n = gun.total_slots;
    for (let i = 0; i < n; i++) {
        const slot = document.createElement("div");
        slot.classList.add("chamber-slot");
        slot.style.setProperty("--angle", `${(360 / n) * i}deg`);
        if (i < gun.pointer) slot.classList.add("fired");
        else if (i === gun.pointer && !isGameOver) slot.classList.add("current");
        const offset = i - gun.pointer;
        if (knownShells && offset >= 0 && knownShells[offset] !== undefined) {
            slot.classList.add(knownShells[offset] ? "known-live" : "known-blank");
            slot.title = knownShells[offset] ? "已知：实弹 🔴" : "已知：空弹 🔵";
        }
        container.appendChild(slot);
    }
    const hub = document.createElement("div");
    hub.className = "chamber-hub";
    hub.title = "剩余弹数";
    hub.innerHTML = `<b>${gun.remaining_slots}</b><i>/${gun.total_slots}</i>`;
    container.appendChild(hub);
}

function updateDuelGunDisplay(state, isGameOver) {
    [state.p1, state.p2].forEach((p, i) => {
        const n = i + 1;
        const gun = state.guns[p.name];
        document.getElementById(`duel-gun-${n}-name`).textContent = p.name;
        document.getElementById(`duel-gun-${n}-remaining`).textContent =
            `${gun.remaining_slots}/${gun.total_slots} 剩余`;
        const liveEl = document.getElementById(`duel-gun-${n}-live`);
        liveEl.innerHTML = isGameOver
            ? `<span class="live-count">实弹: ${gun.live_bullets}</span>`
            : (gun.remaining_live > 0
                ? `<span class="live-count">实弹: ${gun.remaining_live}</span>`
                : "实弹: 0");
        renderChamber(document.getElementById(`duel-gun-${n}-visual`), gun, isGameOver, null);
        const card = document.getElementById(`duel-gun-${n}`);
        card.classList.toggle("active-gun", state.current_player === p.name && !isGameOver);
        card.classList.toggle("dead-gun", !p.is_alive);
    });
}

function updateGunDisplay(gun, isGameOver, knownShells) {
    const remainingEl = document.getElementById("gun-remaining");
    const liveEl = document.getElementById("gun-live");
    const blankEl = document.getElementById("gun-blank");
    remainingEl.textContent = `${gun.remaining_slots}/${gun.total_slots} 剩余`;

    if (isGameOver) {
        liveEl.innerHTML = `<span class="live-count">实弹: ${gun.live_bullets}</span>`;
    } else {
        liveEl.innerHTML = gun.remaining_live > 0
            ? `<span class="live-count">实弹: ${gun.remaining_live}</span>`
            : `实弹: 0`;
    }

    // 恶魔轮盘：空弹数为公开信息
    if (gun.remaining_blank != null && !isGameOver) {
        blankEl.classList.remove("hidden");
        blankEl.textContent = `空弹: ${gun.remaining_blank}`;
    } else {
        blankEl.classList.add("hidden");
    }

    // 弹巢可视化：人类玩家用放大镜得知的弹型打上标记（offset 相对 pointer）
    renderChamber(document.getElementById("chamber-visual"), gun, isGameOver, knownShells);
}

// 单条事件的 DOM 构建（决策详情展开逻辑内聚于此）
function buildEventEntry(e) {
    const div = document.createElement("div");
    div.classList.add("event-entry", e.type);

    // 实弹开火特效
    if (e.type === "fire" && e.is_live) {
        div.classList.add("live-fire");
    }

    // 私有情报：服务端按 viewer 过滤（masked 标志），前端只做样式分层
    if (e.type === "peek") {
        div.classList.add(e.masked ? "private-masked" : "private-own");
    } else if (e.type === "item_use") {
        div.classList.add("item-event");
    }

    const msgSpan = document.createElement("span");
    msgSpan.textContent = e.message || "";
    div.appendChild(msgSpan);

    // 决策详情 - breakdown
    if (e.type === "decision" && e.breakdown && e.breakdown.reanalyzed) {
        const bd = e.breakdown;
        const toggle = document.createElement("span");
        toggle.className = "breakdown-toggle";
        toggle.textContent = "📊 详情";
        toggle.addEventListener("click", () => {
            const existing = div.querySelector(".breakdown-detail");
            if (existing) { existing.remove(); toggle.textContent = "📊 详情"; return; }
            toggle.textContent = "📊 收起";

            const detail = document.createElement("div");
            detail.className = "breakdown-detail";
            if (bd.kernel === "utility") {
                // 恶魔轮盘：效用评估明细
                const fmt = v => (v >= 0 ? "+" : "") + v;
                detail.innerHTML = `
                    <span class="bd-label">策略惯性 S'</span><span class="bd-value">${bd.s_real}</span>
                    <span class="bd-label">实弹概率 p</span><span class="bd-value">${bd.p_live}</span>
                    <span class="bd-label">蝉联价值 T</span><span class="bd-value">${bd.t_value}</span>
                    <span class="bd-label">人格偏置</span><span class="bd-value">${fmt(bd.tie_bias)}</span>
                    <span class="bd-label">对手威胁</span><span class="bd-value">${bd.opp_threat != null ? bd.opp_threat : "—"}</span>
                    <span class="bd-label">威胁偏置</span><span class="bd-value">${bd.threat_bias != null ? fmt(bd.threat_bias) : "—"}</span>
                    <span class="bd-label">λ 击敌/自伤/交权</span><span class="bd-value">${bd.lam_kill} / ${bd.lam_own} / ${bd.lam_give}</span>
                    <span class="bd-label">EU 自击</span><span class="bd-value">${bd.eu_self}</span>
                    <span class="bd-label">EU 击敌</span><span class="bd-value">${bd.eu_enemy}</span>
                    <span class="bd-label">心态修正</span><span class="bd-value">${fmt(bd.mindset_delta)}</span>
                    <span class="bd-label">冷静系数</span><span class="bd-value">${bd.calm_factor}</span>
                    <span class="bd-label">随机扰动</span><span class="bd-value">${fmt(bd.noise_delta)}</span>
                    <span class="bd-label" style="color:var(--accent)">最终效用差</span><span class="bd-value bd-highlight">${fmt(bd.final_diff)} → ${bd.choice === "opponent" ? "击敌" : "自击"}</span>
                `;
            } else {
                // 经典模式：攻击倾向明细
                detail.innerHTML = `
                    <span class="bd-label">策略惯性 S'</span><span class="bd-value">${bd.s_real}</span>
                    <span class="bd-label">实际 P0</span><span class="bd-value">${bd.pr}</span>
                    <span class="bd-label">基础攻击欲</span><span class="bd-value">${bd.base_attack}</span>
                    <span class="bd-label">蝉联期权</span><span class="bd-value">${bd.option_value != null ? "-" + bd.option_value : "—"}</span>
                    <span class="bd-label">心态修正</span><span class="bd-value">${bd.mindset_delta >= 0 ? "+" : ""}${bd.mindset_delta}</span>
                    <span class="bd-label">修正后</span><span class="bd-value">${bd.attack_after_mindset}</span>
                    <span class="bd-label">冷静压制</span><span class="bd-value">${bd.calm_delta >= 0 ? "+" : ""}${bd.calm_delta}</span>
                    <span class="bd-label">压制后</span><span class="bd-value">${bd.attack_after_calm}</span>
                    <span class="bd-label">随机扰动</span><span class="bd-value">${bd.random_delta >= 0 ? "+" : ""}${bd.random_delta}</span>
                    <span class="bd-label" style="color:var(--accent)">最终攻击欲</span><span class="bd-value bd-highlight">${bd.final_attack}</span>
                `;
            }
            div.appendChild(detail);
        });
        div.appendChild(toggle);
    }
    return div;
}

// 增量渲染：只追加新事件，保留已展开的决策详情（事件数回退视为新一局，全量重建）
function updateEventLog(events) {
    const container = document.getElementById("event-log-content");
    const prevCount = STATE._lastEventCount;
    STATE._lastEventCount = events.length;

    const isNewGame = prevCount === 0 || events.length < prevCount;
    if (isNewGame) container.innerHTML = "";
    const startIdx = isNewGame ? 0 : prevCount;

    for (let i = startIdx; i < events.length; i++) {
        container.appendChild(buildEventEntry(events[i]));
    }
    if (events.length > startIdx) container.scrollTop = container.scrollHeight;

    // 新 fire 事件触发动画（新对局的重建不回放动画）
    if (!isNewGame && events.length > prevCount) {
        for (let i = prevCount; i < events.length; i++) {
            const evt = events[i];
            if (evt.type === "fire") {
                triggerGunRecoil();
                triggerChamberFire(evt.is_live);
                if (evt.is_live) triggerKillFlash();
            }
        }
    }
}

function updateActionBar(state) {
    const humanActions = document.getElementById("human-actions");
    const aiActions = document.getElementById("ai-actions");
    if (state.is_over) {
        humanActions.classList.add("hidden");
        aiActions.classList.add("hidden");
        return;
    }
    if (state.needs_human_input) {
        humanActions.classList.remove("hidden");
        aiActions.classList.add("hidden");
        renderHumanItemButtons(state);
        document.querySelectorAll("#human-actions .shoot-action-row .btn").forEach(b => b.disabled = false);
    } else {
        humanActions.classList.add("hidden");
        aiActions.classList.remove("hidden");
        document.getElementById("btn-step").disabled = STATE.isAutoPlaying;
        document.getElementById("btn-auto").disabled = STATE.isAutoPlaying;
    }
}

// 人类道具按钮：道具不消耗回合，使用后仍需射击
function renderHumanItemButtons(state) {
    const row = document.getElementById("human-item-actions");
    const me = [state.p1, state.p2].find(p => p.name === STATE.humanName);
    if (!me || state.item_set === "none" || !me.items || me.items.length === 0) {
        row.classList.add("hidden");
        row.innerHTML = "";
        return;
    }
    // 同类道具合并计数
    const counts = {};
    me.items.forEach(id => { counts[id] = (counts[id] || 0) + 1; });
    row.innerHTML = "";
    Object.keys(counts).forEach(id => {
        const meta = ITEM_META[id] || { name: id, icon: "❔", desc: "" };
        const btn = document.createElement("button");
        btn.className = "btn btn-item";
        btn.title = meta.desc;
        btn.textContent = `${meta.icon} ${meta.name}${counts[id] > 1 ? ` ×${counts[id]}` : ""}`;
        btn.addEventListener("click", () => humanUseItem(id));
        row.appendChild(btn);
    });
    row.classList.remove("hidden");
}

function showGameOver(state) {
    const modal = document.getElementById("game-over-modal");
    modal.classList.remove("hidden");
    document.getElementById("game-over-message").textContent = `🏆 ${state.winner} 获胜！`;
    STATE.lastFinalState = state;   // 战报数据源
    STATE.lastBetResult = null;
    // 竞技场对局提供一键再战（保留选边与下注面板）
    document.getElementById("btn-rematch-arena").classList.toggle("hidden", STATE.mode !== "arena");
    if (state.p1.name === state.winner) {
        document.getElementById("player1-card").classList.add("winner-card");
        document.getElementById("player2-card").classList.add("dead");
    } else {
        document.getElementById("player2-card").classList.add("winner-card");
        document.getElementById("player1-card").classList.add("dead");
    }
    settleArenaBet(state);
}

// ===================== 终局战报 =====================
function openBattleReport() {
    const state = STATE.lastFinalState;
    if (!state) { showToast("暂无可用的战报数据", "error"); return; }
    const paper = document.getElementById("report-paper");
    paper.innerHTML = buildBattleReportHTML(state);
    paper.scrollTop = 0;
    document.getElementById("battle-report").classList.remove("hidden");
}

function closeBattleReport() {
    document.getElementById("battle-report").classList.add("hidden");
}

function buildBattleReportHTML(state) {
    const evts = state.events || [];
    const quote = REPORT_QUOTES[Math.floor(Math.random() * REPORT_QUOTES.length)];
    const now = new Date();
    const dateStr = `${now.getFullYear()} 年 ${now.getMonth() + 1} 月 ${now.getDate()} 日`;
    const modeLabel = MODE_LABELS[state.mode] || state.mode;

    // 统计
    const fires = evts.filter(e => e.type === "fire");
    const liveShots = fires.filter(e => e.is_live).length;
    const blankShots = fires.length - liveShots;
    const selfShots = fires.filter(e => e.action === "self").length;
    const enemyShots = fires.filter(e => e.action === "opponent").length;
    const itemsUsed = evts.filter(e => e.type === "item_use").length;

    // 时间线节点
    const tl = [];
    let shotNo = 0;
    evts.forEach(e => {
        if (e.type === "fire") {
            shotNo += 1;
            const self = e.action === "self";
            const target = self ? "自己" : (e.target_name || "对手");
            const live = !!e.is_live;
            let outcome;
            if (self) outcome = live ? `命中实弹${e.damage > 1 ? ` ×${e.damage}` : ""}，付出代价` : "空枪，蝉联回合";
            else outcome = live ? `命中${target}${e.damage > 1 ? ` ×${e.damage}` : ""}` : "空枪，回合移交";
            tl.push(`
                <div class="tl-node tl-fire ${live ? "live" : "blank"}">
                    <span class="tl-dot"></span>
                    <div class="tl-body">
                        <div class="tl-head">
                            <b>${e.player_name}</b>
                            <span class="tl-tag ${live ? "tag-live" : "tag-blank"}">${live ? "实弹" : "空枪"}</span>
                            <span class="tl-shot">SHOT ${String(shotNo).padStart(2, "0")}</span>
                        </div>
                        <p>${self ? "枪口调转，对准自己" : `抬枪瞄准 ${target}`} —— ${outcome}</p>
                    </div>
                </div>`);
        } else if (e.type === "item_use") {
            const meta = ITEM_META[e.item_id] || { icon: "❔", name: e.item_id || "道具" };
            tl.push(`
                <div class="tl-node tl-item">
                    <span class="tl-dot"></span>
                    <div class="tl-body">
                        <div class="tl-head"><b>${e.player_name}</b><span class="tl-tag tag-item">道具</span></div>
                        <p>${meta.icon} 使用了${meta.name}</p>
                    </div>
                </div>`);
        } else if (e.type === "peek") {
            tl.push(`
                <div class="tl-node tl-item">
                    <span class="tl-dot"></span>
                    <div class="tl-body">
                        <div class="tl-head"><b>${e.player_name}</b><span class="tl-tag tag-item">情报</span></div>
                        <p>${e.message || "窥探了弹巢的秘密"}</p>
                    </div>
                </div>`);
        } else if (e.type === "damage") {
            tl.push(`
                <div class="tl-node tl-damage">
                    <span class="tl-dot"></span>
                    <div class="tl-body"><p>${e.message || `${e.player_name} 受到伤害`}</p></div>
                </div>`);
        } else if (e.type === "result" || e.type === "game_over") {
            const isSys = e.player_name === "系统";
            tl.push(`
                <div class="tl-node ${isSys ? "tl-sys" : "tl-final"}">
                    <span class="tl-dot"></span>
                    <div class="tl-body"><p>${e.message || (e.winner_name ? `${e.winner_name} 获胜` : "")}</p></div>
                </div>`);
        }
    });

    const betLine = STATE.lastBetResult
        ? `<p class="report-bet ${STATE.lastBetResult.win ? "win" : "lose"}">${STATE.lastBetResult.text}</p>`
        : "";

    return `
        <div class="report-masthead">
            <p class="report-eyebrow">THE HOUSE LEDGER · BATTLE REPORT</p>
            <h2 class="report-title">战 报</h2>
            <div class="deco-divider"><span class="deco-line"></span><span class="deco-diamond">◆</span><span class="deco-line"></span></div>
            <p class="report-date">${dateStr} · ${now.toTimeString().slice(0, 5)}</p>
        </div>

        <blockquote class="report-quote">
            <span class="rq-orn">“</span>${quote}<span class="rq-orn">”</span>
        </blockquote>

        <div class="report-match">
            <div class="rm-side">${state.p1.name}<small>${state.p1.character}</small></div>
            <div class="rm-vs">◆</div>
            <div class="rm-side">${state.p2.name}<small>${state.p2.character}</small></div>
        </div>
        <div class="report-meta">
            <span>${modeLabel}</span><span>·</span>
            <span>${state.turn_count} 回合</span><span>·</span>
            <span>${fires.length} 次开火</span><span>·</span>
            <span>局号 ${state.game_id || "-"}</span>
        </div>

        <div class="report-stats">
            <div class="rs-cell"><b>${fires.length}</b><span>开火</span></div>
            <div class="rs-cell"><b>${liveShots}</b><span>实弹</span></div>
            <div class="rs-cell"><b>${blankShots}</b><span>空枪</span></div>
            <div class="rs-cell"><b>${selfShots}</b><span>对己</span></div>
            <div class="rs-cell"><b>${enemyShots}</b><span>对敌</span></div>
            <div class="rs-cell"><b>${itemsUsed}</b><span>道具</span></div>
        </div>

        <p class="report-section-title">— 赛 事 进 程 —</p>
        <div class="report-timeline">${tl.join("")}</div>

        <div class="report-verdict">
            <p class="rv-eyebrow">LA MAIN EST SERVIE · 终审判决</p>
            <h3 class="rv-winner">${state.winner}<small>最终胜者</small></h3>
            ${betLine}
        </div>

        <div class="report-actions">
            <button class="btn btn-secondary" onclick="closeBattleReport()">✕ 关闭战报</button>
        </div>`;
}

// ===================== 游戏操作 =====================
async function humanAction(choice) {
    const btns = document.querySelectorAll("#human-actions .btn");
    btns.forEach(b => { b.disabled = true; b.classList.add("btn-loading"); });
    try {
        const data = await apiPost(`/api/game/${STATE.currentGameId}/action`, { choice });
        updateGameView(data);
    } catch (e) {
        showToast(`操作失败: ${e.message}`, "error");
    }
    btns.forEach(b => { b.disabled = false; b.classList.remove("btn-loading"); });
}

// 使用道具（不消耗回合；服务端校验失败返回 400 + 中文原因）
async function humanUseItem(itemId) {
    const btns = document.querySelectorAll("#human-actions .btn");
    btns.forEach(b => { b.disabled = true; b.classList.add("btn-loading"); });
    try {
        const data = await apiPost(`/api/game/${STATE.currentGameId}/action`, { item_id: itemId });
        updateGameView(data);
    } catch (e) {
        showToast(`${e.message}`, "error");
    }
    btns.forEach(b => { b.disabled = false; b.classList.remove("btn-loading"); });
}

async function autoStep() {
    const btn = document.getElementById("btn-step");
    btn.disabled = true;
    btn.classList.add("btn-loading");
    try {
        const data = await apiPost(`/api/game/${STATE.currentGameId}/auto-step`);
        updateGameView(data);
    } catch (e) {
        showToast(`步进失败: ${e.message}`, "error");
    }
    btn.disabled = false;
    btn.classList.remove("btn-loading");
}

function autoPlay() {
    if (STATE.isAutoPlaying) {
        stopAutoPlay();
        return;
    }
    STATE.isAutoPlaying = true;
    const btnAuto = document.getElementById("btn-auto");
    const btnStep = document.getElementById("btn-step");
    btnAuto.textContent = "⏹ 停止";
    btnAuto.classList.add("btn-accent");
    btnAuto.classList.remove("btn-primary");
    btnStep.disabled = true;
    autoPlayStep();
}

// 自动播放速度：🐢 慢 1.4s / ▶ 标准 0.8s / ⚡ 快 0.35s（播放中切换立即生效）
function setAutoSpeed(btn) {
    STATE.autoSpeedDelay = +btn.dataset.delay;
    $$("#speed-control .speed-btn").forEach(b => b.classList.toggle("active", b === btn));
}

function stopAutoPlay() {
    STATE.isAutoPlaying = false;
    if (STATE.autoPlayTimer) { clearTimeout(STATE.autoPlayTimer); STATE.autoPlayTimer = null; }
    const btnAuto = document.getElementById("btn-auto");
    const btnStep = document.getElementById("btn-step");
    btnAuto.textContent = "⏩ 自动播放";
    btnAuto.classList.remove("btn-accent");
    btnAuto.classList.add("btn-primary");
    btnAuto.disabled = false;
    btnStep.disabled = false;
}

async function autoPlayStep() {
    if (!STATE.isAutoPlaying) return;
    try {
        const data = await apiPost(`/api/game/${STATE.currentGameId}/auto-step`);
        updateGameView(data);
        if (data.is_over) {
            stopAutoPlay();
            return;
        }
        if (data.needs_human_input) {
            stopAutoPlay();
            return;
        }
        STATE.autoPlayTimer = setTimeout(autoPlayStep, STATE.autoSpeedDelay);
    } catch (e) {
        showToast(`自动播放出错: ${e.message}`, "error");
        stopAutoPlay();
    }
}

// ===================== 锦标赛视图 =====================
function updateTournamentView(state) {
    updateSchedule(state);
    updateScoreboard(state);
    updateTournamentCurrent(state);
    const btnStep = document.getElementById("btn-trn-step");
    const btnAll = document.getElementById("btn-trn-all");
    if (state.is_over) {
        showTournamentOver(state);
        btnStep.disabled = true;
        btnAll.disabled = true;
    } else {
        btnStep.disabled = false;
        btnAll.disabled = false;
    }
}

function updateSchedule(state) {
    const list = document.getElementById("schedule-list");
    list.innerHTML = "";
    state.schedule.forEach((m, i) => {
        const div = document.createElement("div");
        div.classList.add("schedule-item");
        if (i < state.match_index) {
            div.classList.add("played");
            const result = state.match_results[i];
            const winner = result ? result.winner : "?";
            div.innerHTML = `#${i + 1} ${m.p1} vs ${m.p2}<br><span class="winner-tag">🏆 ${winner}</span>`;
        } else if (i === state.match_index) {
            div.classList.add("current");
            div.innerHTML = `#${i + 1} <span style="color:var(--accent)">⚡</span> ${m.p1} vs ${m.p2}`;
        } else {
            div.classList.add("pending");
            div.textContent = `#${i + 1} ${m.p1} vs ${m.p2}`;
        }
        list.appendChild(div);
    });
    list.scrollTop = list.scrollHeight;
}

function updateScoreboard(state) {
    const board = document.getElementById("scoreboard");
    const players = state.players.map((p, i) => ({
        ...p, wins: state.wins[i], losses: state.losses[i], kills: state.kills[i]
    }));
    players.sort((a, b) => b.wins - a.wins || b.kills - a.kills || a.losses - b.losses);

    const scoreKey = players.map(p => `${p.name}:${p.wins}-${p.losses}-${p.kills}`).join("|");
    const hasChanged = scoreKey !== STATE._prevScoreKey;
    STATE._prevScoreKey = scoreKey;

    let html = `<table class="scoreboard-table"><thead><tr>
        <th>#</th><th>选手</th><th>人格</th><th>胜</th><th>负</th><th>击杀</th>
    </tr></thead><tbody>`;

    players.forEach((p, rank) => {
        const rc = rank === 0 ? "rank-1" : rank === 1 ? "rank-2" : rank === 2 ? "rank-3" : "";
        const medal = rank === 0 ? "🥇" : rank === 1 ? "🥈" : rank === 2 ? "🥉" : "";
        const highlight = hasChanged ? " score-updated" : "";
        html += `<tr class="${highlight}">
            <td class="${rc}">${medal} ${rank + 1}</td>
            <td><strong>${p.name}</strong></td>
            <td>${p.character}</td>
            <td>${p.wins}</td>
            <td>${p.losses}</td>
            <td>${p.kills}</td>
        </tr>`;
    });
    html += "</tbody></table>";
    board.innerHTML = html;
}

function updateTournamentCurrent(state) {
    const el = document.getElementById("tournament-current");
    if (state.is_over) {
        el.innerHTML = "✅ 全部比赛已完成！";
    } else if (state.current_game) {
        const cg = state.current_game;
        const winner = cg.winner || "?";
        el.innerHTML = `⚡ 上一场：<strong>${cg.p1.name}</strong> vs <strong>${cg.p2.name}</strong> → 🏆 ${winner}`;
    } else {
        el.innerHTML = `准备开始第 <strong>${state.match_index + 1}/${state.total_matches}</strong> 场比赛…`;
    }
}

function showTournamentOver(state) {
    const modal = document.getElementById("tournament-over-modal");
    modal.classList.remove("hidden");
    const rankingDiv = document.getElementById("tournament-final-ranking");
    rankingDiv.className = "ranking-list";
    if (state.ranking && state.ranking.length > 0) {
        rankingDiv.innerHTML = state.ranking.map(r => {
            const medal = r.rank === 1 ? "🥇" : r.rank === 2 ? "🥈" : r.rank === 3 ? "🥉" : "";
            return `<p>${medal} <strong>${r.name}</strong> (${r.character}) — ${r.wins}胜${r.losses}负 ${r.kills}击杀</p>`;
        }).join("");
    }
}

// ===================== 锦标赛操作 =====================
async function tournamentStep() {
    const btn = document.getElementById("btn-trn-step");
    btn.disabled = true;
    btn.classList.add("btn-loading");
    try {
        const data = await apiPost(`/api/tournament/${STATE.currentTournamentId}/step`);
        updateTournamentView(data);
    } catch (e) {
        showToast(`步进失败: ${e.message}`, "error");
    }
    btn.disabled = false;
    btn.classList.remove("btn-loading");
}

async function tournamentRunAll() {
    const btnStep = document.getElementById("btn-trn-step");
    const btnAll = document.getElementById("btn-trn-all");
    btnStep.disabled = true;
    btnAll.disabled = true;
    btnAll.classList.add("btn-loading");
    try {
        const data = await apiPost(`/api/tournament/${STATE.currentTournamentId}/run-all`);
        updateTournamentView(data);
    } catch (e) {
        showToast(`运行失败: ${e.message}`, "error");
    }
    btnStep.disabled = false;
    btnAll.disabled = false;
    btnAll.classList.remove("btn-loading");
}
