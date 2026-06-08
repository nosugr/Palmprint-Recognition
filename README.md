# 掌纹识别门禁系统 · 软件侧

基于 **CompCode（Gabor 竞争编码）** 的掌纹识别门禁系统，包含视觉算法、Flask 后端、SQLite 存储、Vue 3 前端，以及与 STM32 通信的串口桥。识别成功后通过串口驱动 STM32 开锁。

> 本仓库只负责 **PC 这一半**（算法 + 后端 + 前端 + 串口发送侧）。STM32 固件、电磁锁/LED/蜂鸣器电路由嵌入式组负责，按 `docs/INTERFACE_CONTRACT.md` 契约 A 对接。

完整设计见：`AGENTS.md`（上下文）、`DESIGN.md`（课设计划书）、`docs/INTERFACE_CONTRACT.md`（接口契约）、`docs/SOFTWARE_DESIGN.md`（实现蓝图）。

---

## 目录结构

```
algorithm/    纯算法层（零硬件依赖）：preprocess → roi → encode → matcher → template → pipeline
              evaluation.py 评估(EER/ROC/DET)，dataset.py 数据集发现
storage/      SQLite：db.py 建表，repository.py 读写 users/templates/logs
server/       Flask：app.py 应用工厂+启动，routes.py API，stream.py MJPEG 视频流
hardware/     抽象桥：bridge.py（MockBridge/SerialBridge），camera.py（Webcam/Folder）
frontend/     Vue 3 + Naive UI（独立 Vite 工程）：注册 / 验证 / 日志 三页面
scripts/      calibrate.py 标定，generate_demo_dataset.py 合成数据，download_dataset.py 下载
tests/        pytest 单元测试
config.py     全局配置（阈值/ROI/串口/端口）
```

依赖方向严格自下而上：`hardware → algorithm → storage → server → frontend`，算法层永不 import Flask/hardware。

---

## 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.13（仓库自带 `.venv`） | 算法 + 后端 |
| Node.js | ≥ 22 | 前端（仅做完整界面时需要） |
| 包管理 | pnpm（推荐，有 `pnpm-lock.yaml`）或 npm | 前端依赖 |

仓库里已带好 Windows 版虚拟环境 `.venv\`，Python 解释器在 **`.venv\Scripts\python.exe`**。
（注意：`data/README.md` 里写的 `.venv/bin/python` 是 Linux 路径，在 Windows 上用不了，请改用上面的 Windows 路径。）

### 安装 Python 依赖

PowerShell，在项目根目录执行：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖：`flask numpy opencv-python pyserial matplotlib pytest`。

---

## ⚠️ 两个必须先知道的点

1. **最省事：`python run.py` 一键同时启动前后端。**
   不想开两个终端的话，项目根目录直接跑 `python run.py`，会同时拉起后端（5000）和前端（5173），按 Ctrl+C 一次性关闭。下面「运行方式二」是手动分两个终端的等价做法。

2. **前后端端口已统一为 5000。**
   `config.py` 里 `SERVER_PORT` 默认 `5000`，`frontend/vite.config.ts` 的 `/api`、`/video_feed` 也代理到 `http://localhost:5000`，两边对齐，**无需再手动设 `SERVER_PORT`**。

3. **默认用 MockBridge（不接真硬件）。**
   `server/app.py` 的 `main()` 用 `use_serial=False`，开锁命令只打印日志，不发串口。接真 STM32 见文末「接入真实硬件」。

---

## 运行方式一：只跑后端（最快冒烟）

适合先确认算法/后端能起来。无需 Node。

```powershell
# 1) 装依赖（只需一次）
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2)（可选）没有 USB 摄像头时，先生成演示图供后端读取
.venv\Scripts\python.exe scripts\generate_demo_dataset.py

# 3) 启动后端（默认端口 5000）
.venv\Scripts\python.exe -m server.app
```

启动后日志会打印 `server http://0.0.0.0:5000`。用浏览器或 PowerShell 验证健康检查：

```powershell
curl http://localhost:5000/api/health
# 期望：{"ok":true,"data":{"db":true,"camera":true,"hardware":true},"error":null}
```

- **摄像头**：优先用 USB 摄像头（设备 0）。检测不到时自动回退读 `data\demo\person_000` 目录里的图（所以无摄像头时要先跑第 2 步生成演示图）。
- **数据库**：首次启动自动建表，生成根目录 `palmprint.db`。
- 其它接口见 `docs/INTERFACE_CONTRACT.md` 契约 C：`/api/enroll`、`/api/users`、`/api/verify`、`/api/logs` 等。

---

## 运行方式二：前后端完整界面（推荐演示用）

> 嫌麻烦可直接 `python run.py` 一键启动，下面是手动分两个终端的等价做法。

需要 **两个终端**：一个跑后端，一个跑前端。

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
- **注册（Enroll）**：输入姓名，采集多帧掌纹入库（默认 5 张）。
- **验证（Verify）**：抓当前帧比对，命中则触发开锁（Mock 模式下打印日志）。
- **日志（Logs）**：历史识别记录。

---

## 数据集与性能标定（复现 EER/ROC）

CompCode 无需训练，只需「标定阈值 + 评估」。产物写入 `data\reports\`（`calibration.json` / `roc.png` / `det.png`），后端 `config.get_match_threshold()` 会自动读取标定阈值。

### 快速冒烟（合成数据，无需下载）

```powershell
.venv\Scripts\python.exe scripts\generate_demo_dataset.py
.venv\Scripts\python.exe scripts\calibrate.py --data-dir data\demo
```

### 生产级结果（Tongji 官方 ROI，跨 session）

参考结果（150 掌）：**EER ≈ 0.93%，Top-1 ≈ 95%，threshold ≈ 0.43**。下载与解压步骤见 `data/README.md`，标定命令（Windows 写法）：

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
| 前端报错连不上后端 / `/api` 404 | 后端没起来，或没跑在 5000。确认后端日志是 `http://0.0.0.0:5000` |
| `/api/health` 里 `camera:false` | 没插摄像头且没生成演示图。跑 `scripts\generate_demo_dataset.py` |
| 验证/注册报「未检测到清晰掌纹」 | 用合成图或真手时 ROI 提取失败；真演示需对着定位槽放手 |
| `pnpm` 不存在 | 用 `npm install` / `npm run dev` 代替，或先 `npm i -g pnpm` |
| `hardware:true` 但锁不动 | 默认 MockBridge 只打印日志。见上「接入真实硬件」 |
