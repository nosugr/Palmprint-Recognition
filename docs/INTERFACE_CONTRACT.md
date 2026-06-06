# 接口契约 · 掌纹识别门禁系统

> 本文件定义跨模块 / 跨团队 / 跨 Agent 的**边界契约**。任何人（人或 Agent）只要遵守这里的接口，就能独立开发自己负责的部分而不破坏别人。
>
> 契约一旦修改，必须同步通知所有相关方。**不要在实现里偷偷改契约。**

---

## 0. 系统拓扑（前提）

平台已从树莓派改为 **PC + STM32** 双侧：

```
┌─────────────────────────── PC / 笔记本 ───────────────────────────┐
│  USB 摄像头 ──► 视觉算法(OpenCV/NumPy) ──► 匹配判决                 │
│                                              │                     │
│                Flask Web Server ◄──► SQLite  │                     │
│                      ▲                       ▼                     │
│                      │                 HardwareBridge(抽象)         │
│                  浏览器(前端)                 │                     │
└──────────────────────────────────────────────┼─────────────────────┘
                                                │ 串口 (USB-CDC / UART)
                                                ▼
┌─────────────────────────── STM32（嵌入式组负责）──────────────────┐
│  固件解析串口命令 ──► 驱动 电磁锁 / 绿LED / 红LED / 蜂鸣器          │
└────────────────────────────────────────────────────────────────────┘
```

**职责切分：**

| 范围 | 负责方 |
|------|--------|
| 视觉算法、Flask 后端、SQLite、Web 前端、串口命令的**发送侧** | 软件组（本仓库） |
| STM32 固件、电磁锁/LED/蜂鸣器电路、串口命令的**接收与执行侧** | 嵌入式组 |

> ⚠️ 假设标注：以上拓扑基于「STM32 无法运行 OpenCV/Flask，故视觉与 Web 必跑在 PC」推断。若实际部署不同（例如换用其它 SBC），请立即反馈，本契约需相应调整。

---

## 契约 A · 软硬件接口（PC ↔ STM32）

这是平台变更后**唯一受影响**的边界。软件侧只依赖抽象接口 `HardwareBridge`，不关心底层是串口、网络还是 mock。

### A.1 抽象接口（软件侧依赖的契约）

```python
class HardwareBridge(ABC):
    def connect(self) -> None: ...          # 建立连接（打开串口）
    def close(self) -> None: ...            # 释放连接
    def is_alive(self) -> bool: ...         # 链路健康检查
    def unlock(self, duration_ms: int) -> None: ...   # 开锁 duration_ms 毫秒后自动回锁
    def indicate(self, success: bool) -> None: ...    # 结果指示：成功=绿灯+单响；失败=红灯+双响
```

实现类（软件组提供）：

| 实现 | 用途 |
|------|------|
| `MockBridge` | PC 开发期，无硬件。命令打印到日志，`is_alive()` 恒 True |
| `SerialBridge` | 真实串口，通过 `pyserial` 与 STM32 通信，按下方协议编码 |

> 软件层（Flask/算法）只通过 `HardwareBridge` 调用，切换 Mock / Serial 只改一行注入，业务代码零改动。

### A.2 串口线路协议（STM32 侧需实现的接收端）

- **物理层**：USB-CDC 虚拟串口或 UART
- **波特率**：`115200`（默认，可协商）
- **帧格式**：ASCII 行协议，每条命令以 `\n` 结尾，参数用空格分隔
- **编码**：UTF-8 / ASCII

**PC → STM32（命令）**

| 命令 | 含义 | STM32 动作 |
|------|------|-----------|
| `UNLOCK <ms>\n` | 开锁 ms 毫秒 | 继电器吸合/释放，到时自动回锁 |
| `OK\n` | 验证成功指示 | 绿灯亮 + 蜂鸣器单响 |
| `FAIL\n` | 验证失败指示 | 红灯亮 + 蜂鸣器双响 |
| `PING\n` | 健康检查 | 回 `PONG\n` |

**STM32 → PC（响应，可选但推荐）**

| 响应 | 含义 |
|------|------|
| `ACK <CMD>\n` | 已收到并执行某命令 |
| `PONG\n` | 对 `PING` 的应答，用于 `is_alive()` |
| `ERR <msg>\n` | 执行出错 |

> 🔧 **待嵌入式组确认的开放项**（标注为 TODO，确认后回填本表）：波特率是否用 115200、是否需要响应帧、`UNLOCK` 时长由 PC 传还是 STM32 固定、是否需要握手/心跳。在确认前，软件侧 `SerialBridge` 按上表默认实现。

---

## 契约 B · 特征数据格式（算法内部 + 持久化）

所有掌纹特征统一用下面的容器表示，供编码、匹配、入库三处共享。

```python
@dataclass
class PalmTemplate:
    code: bytes          # 打包后的特征位（np.packbits 后的字节）
    mask: bytes          # 有效位掩码（同长度，1=有效）
    height: int          # ROI 高，固定 128
    width: int           # ROI 宽，固定 128
    bits_per_pixel: int  # 每像素编码位数（取决于最终编码方案，见设计文档 S1.2）
    version: str         # 编码版本号，如 "compcode-v1"，用于兼容性校验
```

- **ROI 规格**：灰度 `uint8`，固定 `128 × 128`（性能不足时可降到 `64 × 64`，须同步改 `version`）。
- **距离函数契约**：
  ```python
  def match_distance(a: PalmTemplate, b: PalmTemplate, max_shift: int = 3) -> float
  # 返回归一化掩码汉明距离 ∈ [0, 1]，在 ±max_shift 像素平移内取最小值
  # 仅在 a.mask 与 b.mask 同时有效的位上计算
  # version 不一致时抛 ValueError
  ```
- **判决**：`distance < threshold` 视为同一人。`threshold` 由 EER 标定得到，存配置（见契约 D 的配置项）。

> 具体编码方案（PalmCode / 竞争编码 CompCode）在 `SOFTWARE_DESIGN.md` S1.2 讨论确定，但**无论选哪种，对外都用上面的 `PalmTemplate` 容器**，下游不受影响。

---

## 契约 C · HTTP API（前端 ↔ 后端）

- Base URL：`http://<pc-ip>:5000`
- 请求/响应体均为 JSON（除视频流与页面）
- 所有响应统一结构：`{ "ok": bool, "data": <object|null>, "error": <string|null> }`

| 方法 | 路由 | 说明 | 请求体 | 成功 `data` |
|------|------|------|--------|------------|
| GET | `/` | Web 管理界面入口（生产期由 Flask 返回前端构建产物 `index.html`） | — | HTML |
| GET | `/video_feed` | MJPEG 实时视频流 | — | `multipart/x-mixed-replace` |
| POST | `/api/enroll` | 注册：采集 N 帧并入库 | `{ "name": str, "samples": int=5 }` | `{ "user_id": int, "captured": int, "quality": float }` |
| GET | `/api/users` | 用户列表 | — | `[{ "id", "name", "template_count", "created_at" }]` |
| DELETE | `/api/users/<id>` | 删除用户及其模板 | — | `{ "deleted": int }` |
| POST | `/api/verify` | 取当前帧匹配，命中则触发开锁 | `{}` | `{ "matched": bool, "user": {id,name}\|null, "distance": float, "threshold": float }` |
| GET | `/api/logs` | 识别日志 | query: `?limit=50` | `[{ "id","user_id","matched","distance","created_at" }]` |
| GET | `/api/health` | 系统 + 硬件链路状态 | — | `{ "db": bool, "camera": bool, "hardware": bool }` |

> `/api/verify` 命中后由后端调用 `HardwareBridge.unlock()` 与 `indicate(True)`；未命中调用 `indicate(False)`。前端不直接接触硬件。

**前端形态与对接（Vite + Vue 3 + Naive UI）：**

- 前端是独立的 Vite/Vue 工程（`frontend/`），通过上述 HTTP API 与后端通信，**不直连数据库/硬件**。
- **开发期**：Vite dev server（:5173）经 `server.proxy` 把 `/api`、`/video_feed` 转发到 Flask（:5000），前端不写死后端地址，无 CORS 问题。
- **生产期**：`npm run build` 产出 `frontend/dist/`，由 Flask 静态托管，`/` 返回 `index.html`，全部同源。

---

## 契约 D · 数据库 Schema（SQLite）

```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 每个用户存多条模板（不对二进制编码做"求均值"，见设计文档 S2 说明）
CREATE TABLE templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code            BLOB NOT NULL,
    mask            BLOB NOT NULL,
    height          INTEGER NOT NULL,
    width           INTEGER NOT NULL,
    bits_per_pixel  INTEGER NOT NULL,
    version         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,  -- 未命中为 NULL
    matched     INTEGER NOT NULL,        -- 0/1
    distance    REAL NOT NULL,
    threshold   REAL NOT NULL,
    image_path  TEXT,                    -- 可选，留存现场抓拍
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**配置项**（存 `config.py` 或 `config.json`，非数据库）：

| 配置 | 默认 | 说明 |
|------|------|------|
| `MATCH_THRESHOLD` | 由 EER 标定 | 汉明距离判决阈值 |
| `ROI_SIZE` | `128` | ROI 边长 |
| `ENROLL_SAMPLES` | `5` | 注册采集帧数 |
| `UNLOCK_MS` | `3000` | 开锁时长（毫秒） |
| `SERIAL_PORT` | `auto` | STM32 串口设备 |
| `SERIAL_BAUD` | `115200` | 波特率 |

---

## 契约 E · 模块边界与依赖方向

```
hardware/bridge.py   ← 不依赖任何上层（最底层，可被 mock）
        ▲
algorithm/           ← 纯算法，只依赖 numpy/opencv，不依赖 Flask、不依赖 hardware
        ▲
storage/             ← 依赖 algorithm 的 PalmTemplate；封装 SQLite
        ▲
server/ (Flask)      ← 编排层，依赖 algorithm + storage + hardware，注入 Bridge
        ▲
frontend/            ← 只通过 HTTP API 与后端通信
```

**铁律**：依赖只能自下而上（箭头方向）。`algorithm/` 永远不许 import Flask 或 hardware；这样算法层可在 PC 上脱离一切硬件独立开发与单测。
