# 掌纹识别门禁系统 · 软件侧

基于 **MediaPipe 手部关键点 + CompCode（Gabor 竞争编码）** 的掌纹识别门禁系统，包含视觉算法、Flask 后端、SQLite 存储、Vue 3 前端，以及与 STM32 通信的串口桥。识别成功后通过串口驱动 STM32 开锁。

> 本仓库只负责 **PC 这一半**（算法 + 后端 + 前端 + 串口发送侧）。STM32 固件、电磁锁/LED/蜂鸣器电路由嵌入式组负责，按 `docs/INTERFACE_CONTRACT.md` 契约 A 对接。

完整设计见：`AGENTS.md`（上下文）、`DESIGN.md`（课设计划书）、`docs/INTERFACE_CONTRACT.md`（接口契约）、`docs/SOFTWARE_DESIGN.md`（实现蓝图）、`docs/软硬件连接说明.md`。

---

## 识别流程

```
摄像头帧 → 引导框裁剪 → MediaPipe HandLandmarker（21 关键点）
        → 指缝点 X1/X2 建局部坐标系（Zhang 2017）→ 仿射裁方形 ROI
        → CLAHE 增强 → CompCode 编码（6 方向 Gabor 竞争编码 + 可靠性掩码）
        → 环形方向距离 + 平移搜索匹配 → 距离 < 阈值 ⇒ 开锁
```

- **ROI 定位**：`algorithm/hand_landmarks.py` 用 MediaPipe HandLandmarker 取 21 个手部关键点（替代早期脆弱的 HSV 肤色分割），由四指 MCP 关键点推出两个指缝点，对光照/背景/肤色鲁棒。检测不到手直接拒识。
- **验证多帧融合**：单次验证抓 `CAPTURE_FRAMES`（6）帧，质量最高的前 `VERIFY_PROBE_FRAMES`（3）帧分别与库比对取最小距离，抵消单帧关键点抖动。
- **多模板注册**：每用户每只手保留质量最高的 `MAX_TEMPLATES_PER_HAND`（5）张模板，重复注册自动按质量新旧合并淘汰。
- **手别过滤**：验证时优先只比对同手别（左/右手）的模板，库中无同手别模板时回退全库。
- **阈值**：`config.MATCH_THRESHOLD` 为默认值；存在 `data/reports/calibration.json`（标定脚本产物）时优先读取。

---

## 目录结构

```
algorithm/    纯算法层（零硬件依赖）：preprocess → roi / hand_landmarks → encode → matcher → template
              evaluation.py 评估(EER/ROC/DET)，dataset.py 数据集发现，pipeline.py 批量编码缓存
storage/      SQLite：db.py 建表，repository.py 读写 users/templates/logs
server/       Flask：app.py 应用工厂+启动，routes.py API，stream.py MJPEG 视频流（带关键点调试叠加）
hardware/     抽象桥：bridge.py（MockBridge/SerialBridge），camera.py（Webcam/Folder，支持运行时切换）
frontend/     Vue 3 + Naive UI（独立 Vite 工程）：注册 / 验证 / 日志 三页面
scripts/      calibrate.py 数据集标定，calibrate_live.py 摄像头实采标定，
              generate_demo_dataset.py 合成数据，download_dataset.py 下载
data/models/  hand_landmarker.task（MediaPipe 手部关键点模型，需单独下载，见下）
tests/        pytest 单元测试
config.py     全局配置（阈值/ROI/采集/串口/端口）
run.py        一键同时启动前后端
```

依赖方向严格自下而上：`hardware → algorithm → storage → server → frontend`，算法层永不 import Flask/hardware。

---

## 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.13（仓库自带 `.venv`） | 算法 + 后端 |
| Node.js | ≥ 22 | 前端（仅做完整界面时需要） |
| 包管理 | pnpm（推荐，有 `pnpm-lock.yaml`）或 npm | 前端依赖 |

仓库里已带好 Windows 版虚拟环境 `.venv\`，Python 解释器在 **`.venv\Scripts\python.exe`**。**所有 Python 命令都用这个解释器跑**，不要用系统/Anaconda 的裸 `python`。

### 安装 Python 依赖

PowerShell，在项目根目录执行：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖：`flask numpy opencv-contrib-python mediapipe pyserial matplotlib pytest`。

> ⚠️ **不要再装 `opencv-python`**：mediapipe 依赖 `opencv-contrib-python`，两者共用 `cv2` 目录，同时安装会互相损坏。

### 下载手部关键点模型（必需，一次）

MediaPipe 模型不随 pip 安装，需手动放到 `data\models\hand_landmarker.task`（约 7.8 MB）：

```powershell
New-Item -ItemType Directory -Force data\models | Out-Null
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" -OutFile data\models\hand_landmarker.task
```

缺这个文件后端启动会直接报错。项目路径含中文没关系——代码按字节缓冲加载模型，绕开了 MediaPipe 原生加载器不支持非 ASCII 路径的问题。

---

## ⚠️ 先知道的几个点

1. **最省事：`python run.py` 一键同时启动前后端。**
   会同时拉起后端（5000）和前端（5173），按 Ctrl+C 一次性关闭。下面「运行方式二」是手动分两个终端的等价做法。

2. **前后端端口已统一为 5000。**
   `config.py` 里 `SERVER_PORT` 默认 `5000`，`frontend/vite.config.ts` 的 `/api`、`/video_feed` 也代理到 `http://localhost:5000`，两边对齐，无需再手动设 `SERVER_PORT`。

3. **默认用 MockBridge（不接真硬件）。**
   `server/app.py` 的 `main()` 用 `use_serial=False`，开锁命令只打印日志，不发串口。接真 STM32 见文末「接入真实硬件」。

---

## 运行方式一：只跑后端（最快冒烟）

适合先确认算法/后端能起来。无需 Node。

```powershell
# 1) 装依赖 + 下载模型（只需一次，见上）
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) 启动后端（默认端口 5000）
.venv\Scripts\python.exe -m server.app
```

启动后日志会打印 `server http://0.0.0.0:5000`。验证健康检查：

```powershell
curl http://localhost:5000/api/health
# 期望：{"ok":true,"data":{"db":true,"camera":true,"hardware":{...,"enabled":false}},...}
```

- **摄像头**：优先用 USB 摄像头（默认设备 0，可在前端界面切换并持久化）。检测不到任何摄像头时回退读 `scripts\data\demo\person_000` 目录里的图。注意：合成演示图里没有真实的手，MediaPipe 检测不到，注册/验证会拒识——**真实功能演示必须接摄像头**，回退目录只保证后端能起来。
- **数据库**：首次启动自动建表，生成根目录 `palmprint.db`。
- **主要 API**（详见 `docs/INTERFACE_CONTRACT.md` 契约 C）：
  - `POST /api/enroll` 注册、`POST /api/verify` 验证、`GET /api/users`、`GET /api/logs`
  - `GET /api/preview_status` 实时放手引导（轻量探测，不比对）
  - `GET /api/detect_stats` ROI 检测各阶段成功/拒识计数直方图（诊断用，`?reset=1` 读后清零）
  - `GET /api/cameras`、`POST /api/camera/select` 摄像头探测与切换
  - `GET /api/health` 健康检查

---

## 运行方式二：前后端完整界面（推荐演示用）

> 嫌麻烦可直接 `python run.py` 一键启动，下面是手动分两个终端的等价做法。

**终端 A — 后端**：

```powershell
.venv\Scripts\python.exe -m server.app
```

**终端 B — 前端**：

```powershell
cd frontend
pnpm install      # 或 npm install，只需一次
pnpm dev          # 或 npm run dev
```

Vite 启动后访问它打印的地址（默认 **http://localhost:5173**）。
开发期 Vite 会把 `/api`、`/video_feed` 自动转发到后端 5000，无需配后端地址、无 CORS 问题。

界面三页：
- **注册（Enroll）**：输入姓名，把手掌放入引导框采集多帧掌纹入库（默认 5 张，自动记录左/右手）。
- **验证（Verify）**：抓多帧比对，命中则触发开锁（Mock 模式下打印日志）。
- **日志（Logs）**：历史识别记录（距离/阈值/结果）。

视频流带调试叠加：21 个手部关键点 + 指缝点 X1/X2 + 引导框，方便对位。

---

## 阈值标定（复现 EER/ROC）

CompCode 无需训练，只需「标定阈值 + 评估」。产物写入 `data\reports\`（`calibration.json` / `roc.png` / `det.png`），后端 `config.get_match_threshold()` 会自动读取标定阈值。

### 本机实采标定（推荐，与实际使用条件一致）

仓库自带的 `calibration.json` 是在 Tongji 公开数据集上标定的，与你的摄像头/光照分布不同。用真实使用环境采集标定，阈值和置信度才准：

```powershell
# 至少 3 人（建议 5 人以上），逐人对着摄像头采集后自动算 EER 并写入 calibration.json
.venv\Scripts\python.exe scripts\calibrate_live.py --persons 5 --samples 4
```

### 数据集标定

**快速冒烟（合成数据，无需下载）**——合成图没有真实的手，须加 `--pre-extracted` 跳过自动 ROI：

```powershell
.venv\Scripts\python.exe scripts\generate_demo_dataset.py
.venv\Scripts\python.exe scripts\calibrate.py --data-dir data\demo --pre-extracted
```

**生产级结果（Tongji 官方 ROI，跨 session）**——参考结果（150 掌）：**EER ≈ 0.93%，Top-1 ≈ 95%，threshold ≈ 0.43**。下载与解压步骤见 `data/README.md`：

```powershell
.venv\Scripts\python.exe scripts\calibrate.py `
    --data-dir data\raw\palm_roi\tongji_roi `
    --protocol cross-session --pre-extracted --max-persons 150
```

---

## 运行测试

```powershell
.venv\Scripts\python.exe -m pytest
```

覆盖 `algorithm/` 的预处理、编码、匹配（`tests\test_preprocess.py` / `test_encode.py` / `test_matcher.py`）。算法层零硬件依赖，可在任何机器单测。

---

## 接入真实硬件（STM32）

默认是 Mock，不发串口。接真 STM32 时：

1. 用 Type-C 线把 STM32 连上电脑，确认串口出现（设备管理器里的 COM 口）。
2. 在 `config.py` 设串口：`SERIAL_PORT`（如 `"COM5"`，或保持 `"auto"` 取第一个口）、`SERIAL_BAUD = 115200`。
3. 让后端用 `SerialBridge`：把 `server/app.py` 中 `main()` 里 `create_app()` 改为 `create_app(use_serial=True)`。
   - 注意：串口连接失败会自动回退到 MockBridge（见 `hardware/bridge.py` 的 `create_bridge`），所以接不上时不会崩，但也不会真开锁——看日志确认走的是 Serial 还是 Mock。

串口协议（PC → STM32，ASCII 行协议，`\n` 结尾）见 `docs/INTERFACE_CONTRACT.md` 契约 A：
`UNLOCK <ms>` 开锁、`OK` 成功指示、`FAIL` 失败指示、`PING`→`PONG` 健康检查。

---

## 常见问题

| 现象 | 原因 / 处理 |
|------|------------|
| 后端启动报找不到 `hand_landmarker.task` | 模型没下载。见上「下载手部关键点模型」 |
| 前端报错连不上后端 / `/api` 404 | 后端没起来，或没跑在 5000。确认后端日志是 `http://0.0.0.0:5000` |
| `/api/health` 里 `camera:false` | 没插摄像头且回退目录也没图。插 USB 摄像头，或在前端界面切换摄像头索引 |
| 验证/注册报「请将手掌放入框内」 | MediaPipe 没检测到手：手要完整放入引导框、五指自然张开、光照均匀、离镜头别太远 |
| 同一个人验证距离总贴着阈值 | 仓库自带阈值来自公开数据集。用 `scripts\calibrate_live.py` 在本机实采重新标定 |
| `cv2` 报错 / `__version__` 缺失 | `opencv-python` 和 `opencv-contrib-python` 装重了。两个都卸掉，只重装 `opencv-contrib-python` |
| `pnpm` 不存在 | 用 `npm install` / `npm run dev` 代替，或先 `npm i -g pnpm` |
| `hardware.enabled:false` 但想开锁 | 默认 MockBridge 只打印日志。见上「接入真实硬件」 |
