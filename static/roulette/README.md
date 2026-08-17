# CYBER ROULETTE · 赛博轮盘赌桌（纯前端 UI 片段）

暗黑赛博朋克 × 复古拉斯维加斯风格的欧式轮盘赌桌演示：CSS 3D 转盘 + 滚珠物理动画、金色粒子背景、筹码飞行投注、中奖脉冲光圈与屏幕边缘光晕。零依赖、零构建，单目录即可嵌入任何项目。

## 文件

```
static/roulette/
├── index.html    # 结构：招牌 / 转盘区 / 下注表 / 控制面板
├── style.css     # 视觉与动画（3D 倾斜、霓虹、跑马灯、光效）
├── roulette.js   # 引擎：轮盘几何 / 旋转时间轴 / 粒子 / 下注结算 / 音效
└── README.md     # 本文档
```

## 运行

方式一：直接双击 `index.html` 在浏览器打开（音效与字体需联网加载 Google Fonts）。

方式二：随本项目 FastAPI 服务访问：

```
http://localhost:8000/static/roulette/index.html
```

## 交互流程

1. 右侧筹码架选面值（10 / 50 / 100 / 500）
2. 点击台面任意格子下注 → 筹码从筹码架飞向格子，落点弹跳 +「叮」
3. 点 `SPIN` → 轮盘与滚珠反向旋转、减速、弹跳入槽（约 8 秒）
4. 揭晓：中奖槽位脉冲光圈、屏幕边缘红/黑/绿光晕闪烁、LED 显示结果并结算
5. `清空` 撤回全部投注；`重复上局` 一键复投；右上 🔊 可静音

## 赔付表（返还倍数，含本金）

| 注类型 | 覆盖 | 返还 |
|--------|------|------|
| 直注 `Nº` | 单个数字（含 0） | 36× |
| 红 / 黑 / 单 / 双 / 1-18 / 19-36 | 18 个数字 | 2× |
| 打（1ˢᵗ/2ⁿᵈ/3ʳᵈ 12） | 12 个数字 | 3× |
| 列注（2:1） | 12 个数字 | 3× |

余额仅存于内存（演示用），刷新重置为 1,000。

---

## 接入真实随机数生成逻辑

### 唯一钩子：`spinRNG()`

当前随机数完全在浏览器本地生成，全部逻辑集中在 `roulette.js` 顶部的这个函数：

```js
async function spinRNG() {
    const buf = new Uint32Array(1);
    const limit = Math.floor(0x100000000 / 37) * 37; // 拒绝采样消除模偏差
    let x;
    do {
        crypto.getRandomValues(buf);
        x = buf[0];
    } while (x >= limit);
    S.lastSeed = x.toString(16).padStart(8, "0");
    return x % 37;   // 返回 0-36 的槽位索引（对应 EURO_ORDER）
}
```

**约定**：`async` 返回 `Promise<number>`，取值 `0–36`，表示 `EURO_ORDER` 数组的槽位索引（不是轮盘数字本身；`EURO_ORDER[idx]` 才是开出的数字）。动画开始前调用一次，滚珠最终必然停在返回的槽位——先定结果、后演动画，视觉与结果强一致。

### 接入服务端 RNG（推荐）

把函数体替换为一次后端请求即可，其余代码零改动：

```js
async function spinRNG() {
    const res = await fetch("/api/roulette/spin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bets: Object.fromEntries(S.bets) }),
    });
    if (!res.ok) throw new Error("RNG service unavailable");
    const data = await res.json();          // { "pocket": 17 }
    S.lastSeed = data.commitment ?? data.seed ?? "REMOTE";
    return data.pocket;                     // 0-36 槽位索引
}
```

服务端示例（任何后端等价实现）：

```python
import secrets

EURO_ORDER = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,
              5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]

def fair_index() -> int:
    limit = (1 << 32) // 37 * 37
    while (x := secrets.randbits(32)) >= limit:
        pass
    return x % 37

@app.post("/api/roulette/spin")
async def spin():
    return {"pocket": fair_index()}
```

### 可证明公平（Provable Fairness）

要做成真金产品，服务端应在开赛前公布承诺（commitment）、赛后公布种子：

1. 开奖前：服务端生成 `server_seed`，公布 `sha256(server_seed)` 与 `nonce`
2. 开奖：`pocket = HMAC_SHA256(server_seed, nonce) % 37`（同样做拒绝采样）
3. 赛后：公布 `server_seed`，玩家可自行复算哈希与结果

链上场景可用 Chainlink VRF：请求随机数 → 回调合约写入 `randomWord` → 前端轮询或订阅事件后再调用动画（`spinRNG` 内 `await` 事件即可）。

### 注意事项

- **模偏差**：`rand() % 37` 在 `rand()` 值域非 37 整数倍时分布不均（本代码用拒绝采样修正，替换时请保留等价处理）
- **时序**：`spinRNG()` 在玩家点 SPIN 后、动画启动前调用；若网络慢，函数内可先 `setStatus("请求开奖中…")`，返回后动画照常播放
- **错误处理**：`onSpin()` 未捕获网络异常——建议在 `spinRNG` 内部 catch 后 `throw`，并在此处 `try/catch` 恢复按钮状态
- **不要用 `Math.random()`**：可被玩家在控制台预测/覆写，仅适合纯演示

## 自定义

| 需求 | 位置 |
|------|------|
| 旋转时长/圈数 | `roulette.js` → `S.spinDur`、`SPIN.W_TURNS / B_TURNS` |
| 转盘倾角 | `roulette.js` → `tick()` 中 `rotateX(52deg)`（同步 `style.css` 的 `.rim/.ball-track`） |
| 配色主题 | `style.css` → `:root` CSS 变量 |
| 槽序（欧式→美式双零） | `EURO_ORDER` + `SEG = 360/38` + conic 生成循环，37 改 38 |
| 粒子密度 | `initParticles()` → `DUST_N / CONF_N` |
