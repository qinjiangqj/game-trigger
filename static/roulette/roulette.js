/* ============================================================
   CYBER ROULETTE — 前端引擎
   模块：轮盘几何 / 3D 旋转时间轴 / 粒子背景 / 筹码动画 / 音效 / 下注结算
   ============================================================ */
"use strict";

/* ---------- 轮盘常量（欧式单零） ---------- */
const EURO_ORDER = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
];
const REDS = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const SEG = 360 / 37;

/* 几何（px，基于 560 设计稿；CSS 同步） */
const GEO = { TRACK_R: 228, POCKET_R: 188, LABEL_R: 204, BULB_R: 252, SIZE: 560 };

const $ = (s, ctx = document) => ctx.querySelector(s);
const $$ = (s, ctx = document) => [...ctx.querySelectorAll(s)];
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOutQuart = p => 1 - Math.pow(1 - p, 4);
const easeOutCubic = p => 1 - Math.pow(1 - p, 3);
const smooth = p => p * p * (3 - 2 * p);

/* ---------- 状态 ---------- */
const S = {
    wheelAngle: 0,
    spinning: false,
    spinT0: 0,
    spinDur: 8200,
    spinIdx: 0,          // 目标槽索引（动画前已定）
    ballAngle: 0,
    ballR: GEO.TRACK_R,
    ballVisible: false,
    lastBouncePhase: 0,
    balance: 1000,
    chip: 50,             // 当前选中面值
    bets: new Map(),
    lastBets: null,
    muted: false,
    lastSeed: "--------",
};

/* ============================================================
   RNG 钩子 —— 接入真实随机数请只改这一个函数（见 README.md）
   返回 Promise<number>：0-36 的槽位索引（对应 EURO_ORDER）
   ============================================================ */
async function spinRNG() {
    const buf = new Uint32Array(1);
    const limit = Math.floor(0x100000000 / 37) * 37; // 拒绝采样消除模偏差
    let x;
    do {
        crypto.getRandomValues(buf);
        x = buf[0];
    } while (x >= limit);
    S.lastSeed = x.toString(16).padStart(8, "0");
    return x % 37;
}

/* ============================================================
   构建轮盘
   ============================================================ */
function pocketColor(n) {
    if (n === 0) return "var(--green)";
    return REDS.has(n) ? "var(--red)" : "var(--black-pocket)";
}

function buildWheel() {
    const conic = $("#conicFace");
    const stops = [];
    for (let i = 0; i < 37; i++) {
        const a0 = i * SEG - SEG / 2;
        stops.push(`${pocketColor(EURO_ORDER[i])} ${a0}deg ${a0 + SEG}deg`);
    }
    conic.style.background = `conic-gradient(from 0deg, ${stops.join(",")})`;

    /* 金属分隔辐条 */
    const seps = [];
    for (let i = 0; i < 37; i++) {
        const a = i * SEG - SEG / 2;
        seps.push(`#e8c667cc ${a - 0.35}deg ${a + 0.35}deg`);
        seps.push(`transparent ${a + 0.35}deg ${(a - SEG / 2 + SEG) - 0.35}deg`);
    }
    $("#seps").style.background = `conic-gradient(from 0deg, ${seps.join(",")})`;

    /* 数字标签 */
    const labels = $("#labels");
    labels.innerHTML = "";
    EURO_ORDER.forEach((n, i) => {
        const s = document.createElement("span");
        s.textContent = n;
        s.style.transform = `rotate(${i * SEG}deg) translateY(-${GEO.LABEL_R}px)`;
        labels.appendChild(s);
    });

    /* 跑马灯泡 */
    const bulbs = $("#bulbs");
    bulbs.innerHTML = "";
    for (let i = 0; i < 36; i++) {
        const b = document.createElement("span");
        b.style.setProperty("--a", `${i * 10}deg`);
        b.style.setProperty("--i", i);
        bulbs.appendChild(b);
    }
}

/* ============================================================
   旋转时间轴（rAF 驱动）
   ============================================================ */
const SPIN = { W_TURNS: 1350, B_TURNS: 2160, P_TRACK: 0.55, P_DROP: 0.80, P_LOCK: 0.90 };

function wheelAngleAt(t) {
    const p = clamp(t / S.spinDur, 0, 1);
    return S._w0 + SPIN.W_TURNS * easeOutQuart(p);
}

function ballFreeAngleAt(t) {
    const q = clamp(t / (S.spinDur * SPIN.P_DROP), 0, 1);
    return S._b0 - SPIN.B_TURNS * easeOutCubic(q);
}

function ballStateAt(t) {
    const T = S.spinDur;
    const pocketOffset = S.spinIdx * SEG;
    let angle, radius = GEO.TRACK_R;

    if (t < T * SPIN.P_TRACK) {
        angle = ballFreeAngleAt(t);
    } else if (t < T * SPIN.P_DROP) {
        const q = smooth((t - T * SPIN.P_TRACK) / (T * (SPIN.P_DROP - SPIN.P_TRACK)));
        angle = ballFreeAngleAt(t);
        const bounce = Math.abs(Math.sin(q * Math.PI * 3.2)) * 15 * (1 - q);
        radius = lerp(GEO.TRACK_R, GEO.POCKET_R, q) + bounce;
        bounceTick(q);
    } else if (t < T * SPIN.P_LOCK) {
        const q = smooth((t - T * SPIN.P_DROP) / (T * (SPIN.P_LOCK - SPIN.P_DROP)));
        const lock = wheelAngleAt(t) + pocketOffset;
        angle = lerpAngle(ballFreeAngleAt(T * SPIN.P_DROP), lock, q);
        radius = GEO.POCKET_R;
    } else {
        angle = wheelAngleAt(t) + pocketOffset;
        radius = GEO.POCKET_R;
    }
    return { angle, radius };
}

/* 角度插值（走最短弧） */
function lerpAngle(a, b, t) {
    let d = (b - a) % 360;
    if (d > 180) d -= 360;
    if (d < -180) d += 360;
    return a + d * t;
}

function bounceTick(q) {
    const phase = Math.floor(q * 3.2);
    if (phase !== S.lastBouncePhase) {
        S.lastBouncePhase = phase;
        sfxTick();
    }
}

/* ---------- 主循环 ---------- */
function tick(now) {
    /* 轮盘 */
    if (S.spinning) {
        const t = now - S.spinT0;
        S.wheelAngle = wheelAngleAt(t);
        const b = ballStateAt(t);
        S.ballAngle = b.angle;
        S.ballR = b.radius;
        if (t >= S.spinDur) {
            S.spinning = false;
            onSpinEnd();
        }
    } else {
        S.wheelAngle += 0.05; // idle 慢转
        if (S.ballVisible) S.ballAngle += 0.05;
    }

    $("#wheel").style.transform = `rotateX(52deg) rotateZ(${S.wheelAngle}deg)`;
    if (S.ballVisible) {
        $("#ball").style.transform =
            `rotateX(52deg) rotateZ(${S.ballAngle}deg) translateY(-${S.ballR}px) translate(-50%, -50%)`;
    }

    requestAnimationFrame(tick);
}

/* ============================================================
   开局
   ============================================================ */
async function onSpin() {
    if (S.spinning) return;
    if (S.bets.size === 0) { toast("请先在台面下注"); return; }

    S.spinning = true;
    S.lastBets = new Map(S.bets);
    lockUI(true);
    setStatus(`NO MORE BETS · SPINNING…`, true);

    S.spinIdx = await spinRNG();
    setStatus(`RNG: LOCAL-CSPRNG · SEED 0x${S.lastSeed.toUpperCase()} · NO MORE BETS`, true);

    S._w0 = S.wheelAngle;
    S._b0 = S.ballAngle;
    S.spinT0 = performance.now();
    S.ballVisible = true;
    $("#ball").hidden = false;
    S.lastBouncePhase = -1;
    $("#bulbs").classList.add("fast");
}

function onSpinEnd() {
    $("#bulbs").classList.remove("fast");
    reveal(EURO_ORDER[S.spinIdx]);
    lockUI(false);
}

/* ---------- 结果揭晓 ---------- */
function reveal(number) {
    const idx = EURO_ORDER.indexOf(number);
    const color = number === 0 ? "green" : REDS.has(number) ? "red" : "black";

    /* LED 与历史 */
    const led = $("#ledNum");
    led.textContent = number;
    led.className = "led-num " + color;
    $("#ledColor").textContent =
        number === 0 ? "ZERO · LA PARTAGE" : color === "red" ? "ROUGE" : "NOIR";
    pushHistory(number, color);

    /* 转盘脉冲光圈（挂在轮盘内，随盘旋转） */
    const pulse = $("#winPulse");
    pulse.style.transform =
        `rotate(${idx * SEG}deg) translateY(-${GEO.POCKET_R}px) translate(-50%, -50%)`;
    pulse.hidden = false;
    pulse.classList.remove("on");
    void pulse.offsetWidth;
    pulse.classList.add("on");
    setTimeout(() => { pulse.hidden = true; }, 3600);

    /* 屏幕边缘光晕（红/黑/绿） */
    const edge = $("#edge-glow");
    edge.style.setProperty("--eg",
        color === "red" ? "#ff2d55dd" : color === "black" ? "#8a93c8cc" : "#2fff9add");
    edge.classList.remove("on");
    void edge.offsetWidth;
    edge.classList.add("on");

    /* 下注表命中格闪烁 */
    $$("#layout .cell").forEach(c => c.classList.remove("win-hit"));
    const hits = winningBets(number);
    hits.forEach(id => {
        const cell = $(`#layout .cell[data-bet="${id}"]`);
        if (cell) cell.classList.add("win-hit");
    });

    /* 结算（只对实际下注的命中项） */
    const payout = hits
        .filter(id => S.bets.has(id))
        .reduce((sum, id) => sum + betsPayout(id) * S.bets.get(id), 0);
    if (payout > 0) {
        S.balance += payout;
        flashBalance();
        toast(`🎉 Nº ${number} — 中奖返还 +${payout.toLocaleString()}`);
        sfxWin();
    } else {
        toast(`Nº ${number} — 本局未中，再接再厉`);
        sfxLose();
    }
    updateBalance();

    S.bets.clear();
    renderAllStacks();
    setStatus(`Nº ${number} ${color.toUpperCase()} · PAYOUT ${payout > 0 ? "+" + payout.toLocaleString() : "0"} · AWAITING BETS`);
}

function pushHistory(number, color) {
    const h = $("#history");
    const chip = document.createElement("span");
    chip.className = "hchip " + color;
    chip.textContent = number;
    h.prepend(chip);
    while (h.children.length > 12) h.lastChild.remove();
}

/* ---------- 赔付（返还倍数，含本金） ---------- */
function betsPayout(id) {
    if (id.startsWith("n")) return 36;
    if (["red", "black", "odd", "even", "low", "high"].includes(id)) return 2;
    if (id.startsWith("col") || id.startsWith("dozen")) return 3;
    return 0;
}

function winningBets(n) {
    const hits = [`n${n}`];
    if (n === 0) return hits;
    if (REDS.has(n)) hits.push("red"); else hits.push("black");
    if (n % 2 === 0) hits.push("even"); else hits.push("odd");
    if (n <= 18) hits.push("low"); else hits.push("high");
    hits.push(n % 3 === 0 ? "col3" : n % 3 === 2 ? "col2" : "col1");
    hits.push(n <= 12 ? "dozen1" : n <= 24 ? "dozen2" : "dozen3");
    return hits;
}

/* ============================================================
   下注表
   ============================================================ */
function buildLayout() {
    const grid = $("#layout");
    const cells = [];
    const add = (betId, label, cls, col, row, cs = 1, rs = 1) => {
        cells.push({ betId, label, cls, col, row, cs, rs });
    };

    add("n0", "0", "green", 1, 1, 1, 3);
    for (let c = 0; c < 12; c++) {
        const n3 = c * 3 + 3, n2 = c * 3 + 2, n1 = c * 3 + 1;
        add(`n${n3}`, n3, colorCls(n3), c + 2, 1);
        add(`n${n2}`, n2, colorCls(n2), c + 2, 2);
        add(`n${n1}`, n1, colorCls(n1), c + 2, 3);
    }
    add("col3", "2:1", "black outside", 13, 4);
    add("col2", "2:1", "black outside", 12, 4);
    add("col1", "2:1", "black outside", 11, 4);
    add("dozen1", "1ˢᵗ 12", "black outside", 2, 5, 4);
    add("dozen2", "2ⁿᵈ 12", "black outside", 6, 5, 4);
    add("dozen3", "3ʳᵈ 12", "black outside", 10, 5, 4);
    add("low", "1-18", "black outside", 2, 6, 2);
    add("even", "双 EVEN", "black outside", 4, 6, 2);
    add("red", "◆ 红", "red outside", 6, 6, 2);
    add("black", "◆ 黑", "black outside", 8, 6, 2);
    add("odd", "单 ODD", "black outside", 10, 6, 2);
    add("high", "19-36", "black outside", 12, 6, 2);

    grid.innerHTML = "";
    cells.forEach(c => {
        const d = document.createElement("div");
        d.className = `cell ${c.cls}`;
        d.dataset.bet = c.betId;
        d.style.gridColumn = `${c.col} / span ${c.cs}`;
        d.style.gridRow = `${c.row} / span ${c.rs}`;
        d.innerHTML = `<span class="cell-label">${c.label}</span><span class="stack" hidden></span>`;
        d.addEventListener("click", () => placeBet(c.betId, d));
        grid.appendChild(d);
    });
}

function colorCls(n) { return n === 0 ? "green" : REDS.has(n) ? "red" : "black"; }

let _targetCell = null;   // 最近点击的投注格（筹码飞行终点）

function placeBet(betId, cell) {
    if (S.spinning) return;
    if (S.balance < S.chip) { toast("余额不足，换个面值或清空重下"); return; }
    _targetCell = cell;

    S.balance -= S.chip;
    updateBalance();
    S.bets.set(betId, (S.bets.get(betId) || 0) + S.chip);

    const stack = $(".stack", cell);
    renderStack(stack, S.bets.get(betId));
    flyChip(() => {
        /* 到达：落点弹跳 + 叮 */
        stack.hidden = false;
        stack.classList.remove("land");
        void stack.offsetWidth;
        stack.classList.add("land");
        sfxDing();
    });
}

function renderStack(stack, amount) {
    stack.hidden = false;
    const cls = amount >= 500 ? "c500" : amount >= 100 ? "c100" : amount >= 50 ? "c50" : "c10";
    stack.innerHTML = `<span class="coin ${cls}">${amount >= 1000 ? (amount / 1000).toFixed(1).replace(/\.0$/, "") + "k" : amount}</span>`;
}

function renderAllStacks() {
    $$("#layout .cell").forEach(cell => {
        const stack = $(".stack", cell);
        const amt = S.bets.get(cell.dataset.bet);
        if (amt) renderStack(stack, amt);
        else { stack.hidden = true; stack.innerHTML = ""; }
    });
}

/* ---------- 筹码飞行（FLIP：筹码架 → 投注格） ---------- */
function flyChip(onLand) {
    const from = $(".chip.active") || $(".chip");
    const to = _targetCell;
    if (!from || !to) { onLand(); return; }

    const fromRect = from.getBoundingClientRect();
    const toRect = to.getBoundingClientRect();

    const fly = document.createElement("div");
    fly.className = "fly-chip";
    fly.textContent = S.chip;
    fly.style.background = chipBg(S.chip);
    $("#fly-layer").appendChild(fly);

    const x0 = fromRect.left + fromRect.width / 2 - 26;
    const y0 = fromRect.top + fromRect.height / 2 - 26;
    const x1 = toRect.left + toRect.width / 2 - 26;
    const y1 = toRect.top + toRect.height / 2 - 26;

    fly.animate([
        { transform: `translate(${x0}px, ${y0}px) scale(1) rotate(0deg)` },
        { transform: `translate(${(x0 + x1) / 2}px, ${(y0 + y1) / 2 - 70}px) scale(1.22) rotate(160deg)`, offset: .55 },
        { transform: `translate(${x1}px, ${y1}px) scale(.55) rotate(340deg)` },
    ], { duration: 460, easing: "cubic-bezier(.25,.7,.3,1)" })
        .onfinish = () => { fly.remove(); onLand(); };
}

function chipBg(v) {
    return {
        10: "radial-gradient(circle at 35% 30%, #6ff5ff, #0e7c8a 75%)",
        50: "radial-gradient(circle at 35% 30%, #ff7ec2, #a11668 75%)",
        100: "radial-gradient(circle at 35% 30%, #ffe08a, #8a6d1a 75%)",
        500: "radial-gradient(circle at 35% 30%, #b78bff, #4b2a8a 75%)",
    }[v];
}

/* ---------- 筹码选择 / 余额 ---------- */
const DENOMS = [10, 50, 100, 500];

function buildChips() {
    const box = $("#chips");
    box.innerHTML = "";
    DENOMS.forEach(v => {
        const c = document.createElement("button");
        c.className = "chip" + (v === S.chip ? " active" : "");
        c.style.background = chipBg(v);
        c.textContent = v;
        c.addEventListener("click", () => {
            S.chip = v;
            $$(".chip").forEach(x => x.classList.remove("active"));
            c.classList.add("active");
        });
        box.appendChild(c);
    });
}

function updateBalance() {
    $("#balance").textContent = S.balance.toLocaleString();
}
function flashBalance() {
    const b = $("#balance");
    b.classList.remove("flash");
    void b.offsetWidth;
    b.classList.add("flash");
}

/* ---------- 控制 ---------- */
function clearBets() {
    if (S.spinning || S.bets.size === 0) return;
    let refund = 0;
    S.bets.forEach(v => refund += v);
    S.balance += refund;
    S.bets.clear();
    renderAllStacks();
    updateBalance();
    setStatus("BETS CLEARED · AWAITING BETS…");
}

function rebet() {
    if (S.spinning || !S.lastBets || S.lastBets.size === 0) { toast("没有可重复的注单"); return; }
    let total = 0;
    S.lastBets.forEach(v => total += v);
    if (S.balance < total) { toast("余额不足以重复上局"); return; }
    S.balance -= total;
    S.bets = new Map(S.lastBets);
    renderAllStacks();
    updateBalance();
    setStatus("REBET PLACED · READY TO SPIN");
    sfxDing();
}

function lockUI(locked) {
    $("#layout").classList.toggle("locked", locked);
    $("#btnSpin").disabled = locked;
    $("#btnClear").disabled = locked;
    $("#btnRebet").disabled = locked;
    $("#btnSpin").textContent = locked ? "NO MORE BETS…" : "SPIN ⟳";
}

function setStatus(text, alert = false) {
    const el = $("#statusBar");
    el.textContent = text;
    el.classList.toggle("alert", alert);
}

function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove("show"), 2600);
}

/* ============================================================
   WebAudio 合成音效（无外部资源）
   ============================================================ */
let AC = null;

function ensureAudio() {
    if (S.muted) return null;
    if (!AC) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        AC = new Ctx();
    }
    if (AC.state === "suspended") AC.resume();
    return AC;
}

function tone(freq, dur, type = "sine", gain = .12, delay = 0) {
    const ctx = ensureAudio();
    if (!ctx) return;
    const t0 = ctx.currentTime + delay;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    g.gain.setValueAtTime(gain, t0);
    g.gain.exponentialRampToValueAtTime(.0001, t0 + dur);
    osc.connect(g).connect(ctx.destination);
    osc.start(t0);
    osc.stop(t0 + dur + .02);
}

function sfxDing()  { tone(2093, .16, "triangle", .1); tone(3136, .09, "sine", .05); }
function sfxTick()  { tone(1200 + Math.random() * 300, .04, "square", .025); }
function sfxWin()   { [523, 659, 784, 1047].forEach((f, i) => tone(f, .3, "triangle", .09, i * .09)); }
function sfxLose()  { tone(196, .35, "sine", .08); tone(147, .4, "sine", .06, .12); }

/* ============================================================
   粒子背景（金色尘埃 + 霓虹纸屑）
   ============================================================ */
function initParticles() {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const cv = $("#fx");
    const ctx = cv.getContext("2d");
    let W, H, dpr;

    const resize = () => {
        dpr = Math.min(devicePixelRatio || 1, 2);
        W = innerWidth; H = innerHeight;
        cv.width = W * dpr; cv.height = H * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    addEventListener("resize", resize);

    const DUST_N = Math.round(innerWidth / 26);
    const CONF_N = 9;
    const rand = (a, b) => a + Math.random() * (b - a);

    const dust = Array.from({ length: DUST_N }, () => ({
        x: rand(0, innerWidth), y: rand(0, innerHeight),
        r: rand(.8, 2.6), vy: rand(14, 38), sway: rand(.4, 1.4),
        tw: rand(0, Math.PI * 2), tws: rand(.8, 2.4),
    }));
    const CONF_COLORS = ["#f5c518", "#ff2d95", "#19e6ff", "#ffe9a0"];
    const conf = Array.from({ length: CONF_N }, () => ({
        x: rand(0, innerWidth), y: rand(-innerHeight, 0),
        w: rand(5, 9), h: rand(8, 14), vy: rand(18, 42),
        rot: rand(0, Math.PI), vr: rand(-1.5, 1.5),
        sway: rand(.6, 1.8), color: CONF_COLORS[Math.floor(rand(0, 4))],
    }));

    let last = performance.now();
    (function loop(now) {
        const dt = Math.min(.05, (now - last) / 1000);
        last = now;
        ctx.clearRect(0, 0, W, H);
        const t = now / 1000;

        for (const d of dust) {
            d.y += d.vy * dt;
            d.x += Math.sin(t * d.sway + d.tw) * .3;
            if (d.y > H + 4) { d.y = -4; d.x = rand(0, W); }
            const a = .25 + .55 * Math.abs(Math.sin(t * d.tws + d.tw));
            ctx.globalAlpha = a;
            ctx.fillStyle = "#f5c518";
            ctx.beginPath();
            ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
            ctx.fill();
        }

        for (const c of conf) {
            c.y += c.vy * dt;
            c.x += Math.sin(t * c.sway) * .5;
            c.rot += c.vr * dt;
            if (c.y > H + 20) { c.y = -20; c.x = rand(0, W); }
            ctx.globalAlpha = .5;
            ctx.save();
            ctx.translate(c.x, c.y);
            ctx.rotate(c.rot);
            ctx.fillStyle = c.color;
            ctx.fillRect(-c.w / 2, -c.h / 2, c.w, c.h * Math.abs(Math.sin(t * c.sway + c.rot)));
            ctx.restore();
        }
        ctx.globalAlpha = 1;
        requestAnimationFrame(loop);
    })(last);
}

/* ============================================================
   自适应缩放
   ============================================================ */
function fitWheel() {
    const side = $(".wheel-side");
    if (!side) return;
    const w = side.getBoundingClientRect().width;
    const ws = clamp(w / (GEO.SIZE + 24), .45, 1);
    $(".wheel-scale").style.setProperty("--ws", ws.toFixed(3));
}

/* ============================================================
   启动
   ============================================================ */
function init() {
    buildWheel();
    buildLayout();
    buildChips();
    updateBalance();

    $("#btnSpin").addEventListener("click", onSpin);
    $("#btnClear").addEventListener("click", clearBets);
    $("#btnRebet").addEventListener("click", rebet);
    $("#btnMute").addEventListener("click", () => {
        S.muted = !S.muted;
        $("#btnMute").textContent = S.muted ? "🔇" : "🔊";
    });
    /* 首次交互解锁 AudioContext（浏览器自动播放策略） */
    addEventListener("pointerdown", () => ensureAudio(), { once: true });

    fitWheel();
    addEventListener("resize", fitWheel);
    initParticles();

    $("#bulbs").classList.add("run");
    requestAnimationFrame(tick);
}

document.addEventListener("DOMContentLoaded", init);
