# Palmprint_Recognition 系统架构文档

## 1. 整体架构（5 层，自下而上）

```
┌─────────────────────────────────────────────────────────────────────┐
│  frontend/          Vue 3 + Naive UI（仅通过 HTTP 通信）            │
│                     注册/验证/日志三大页面，MJPEG 实时预览           │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ HTTP API (localhost:5000)
┌──────────────────────────────────▼──────────────────────────────────┐
│  server/            Flask 编排层（依赖注入）                         │
│                     路由 · 视频推流 · 多帧选优 · 业务流程编排        │
└────────────┬───────────────────────────────────────────┬────────────┘
             │                                           │
┌────────────▼────────────────────┐    ┌─────────────────▼────────────┐
│  storage/      SQLite 持久化    │    │  hardware/   硬件抽象层       │
│  users / templates / logs CRUD  │    │  摄像头抽象 · 串口桥接        │
└────────────┬────────────────────┘    └─────────────────▲────────────┘
             │                                           │
┌────────────▼───────────────────────────────────────────┴────────────┐
│  algorithm/        纯算法层（零硬件依赖，只吃 numpy 数组）           │
│  预处理 · ROI提取 · CompCode编码 · 匹配 · 评估                     │
└─────────────────────────────────────────────────────────────────────┘
```

**依赖规则**：严格自下而上，`algorithm/` 永远不 import Flask 或 hardware，可在任意机器独立单测。

---

## 2. 各层职责与核心文件

### 2.1 algorithm/ — 纯算法层

| 文件 | 职责 |
|------|------|
| `roi.py` | 手掌分割（OTSU+形态学）→ 掌心定位（距离变换）→ 指缝检测（X1/X2）→ 仿射裁剪 128×128 ROI |
| `preprocess.py` | 灰度化 → 双边滤波 → CLAHE 直方图均衡 → 有效性掩码 |
| `encode.py` | 6 方向 Gabor 滤波 → CompCode 竞争编码（3 bit/pixel）→ 可靠性掩码 |
| `matcher.py` | 环形方向距离 + ±6 像素 shift matching + 掩码归一化 |
| `template.py` | `PalmTemplate` 数据结构（code/mask/quality/version）与序列化 |
| `pipeline.py` | 批量编码与缓存管理 |
| `evaluation.py` | EER/FAR/FRR/ROC/DET 评估指标计算 |
| `dataset.py` | 数据集发现与按人/按掌分组 |

### 2.2 storage/ — 持久化层

| 文件 | 职责 |
|------|------|
| `db.py` | SQLite 连接管理，建表（users / palm_templates / access_logs） |
| `repository.py` | `UserRepo` / `TemplateRepo` / `LogRepo` 的 CRUD 操作 |

### 2.3 server/ — Flask 编排层

| 文件 | 职责 |
|------|------|
| `app.py` | 应用工厂 + 依赖注入（bridge / camera / repo） |
| `routes.py` | HTTP API 路由：注册 / 验证 / 用户管理 / 日志 / 摄像头切换 |
| `stream.py` | MJPEG 视频推流生成器 |

### 2.4 hardware/ — 硬件抽象层

| 文件 | 职责 |
|------|------|
| `bridge.py` | `HardwareBridge` 接口 + `MockBridge`（空壳）+ `SerialBridge`（串口通信） |
| `camera.py` | `WebcamCamera`（实时摄像头）/ `FolderCamera`（图片文件夹）/ `SwitchableCamera`（动态切换） |
| `probe.py` | 探测系统可用摄像头列表 |

### 2.5 frontend/ — Vue 3 前端

| 文件 | 职责 |
|------|------|
| `App.vue` | 主布局，Tab 切换：注册 / 验证 / 日志 |
| `views/Enroll.vue` | 注册页：输入姓名 → 采集掌纹 → 提交 |
| `views/Verify.vue` | 验证页：实时预览 → 点击验证 → 显示结果 |
| `views/Logs.vue` | 日志页：分页查看识别记录 |
| `components/CameraView.vue` | 摄像头画面组件 + 实时手掌状态引导 |
| `api/index.ts` | HTTP API 封装（fetch 调用 Flask 后端） |

---

## 3. 完整链路：从用户操作到 STM32 开锁

### 3.1 注册流程

```
用户输入姓名，点击"采集"
    │
    ▼
frontend: POST /api/enroll  {name, images[base64]}
    │
    ▼
server/routes.py: _capture_encode()
    ├── 抓取 6 帧（间隔 60ms）
    ├── 每帧独立做 ROI 提取
    └── 按拉普拉斯方差选最清晰帧
    │
    ▼
algorithm/preprocess.py: preprocess()
    ├── 灰度化
    ├── 双边滤波去噪
    ├── CLAHE 直方图均衡
    └── 生成有效性掩码
    │
    ▼
algorithm/encode.py: encode()
    ├── 6 方向 Gabor 滤波
    ├── CompCode 竞争编码（每像素 0-5，3 bit）
    └── 可靠性掩码（屏蔽平坦区）
    │
    ▼
algorithm/template.py: PalmTemplate 打包
    │
    ▼
storage/repository.py: TemplateRepo.save()
    └── SQLite: palm_templates 表
    │
    ▼
返回 {ok: true, user_id, quality_score}
```

### 3.2 验证流程（核心链路）

```
用户点击"验证"
    │
    ▼
frontend: POST /api/verify
    │
    ▼
server/routes.py: _capture_encode()
    ├── 抓取 6 帧，选最清晰帧
    ├── 预处理 → 编码 → PalmTemplate
    └── 返回 probe_template
    │
    ▼
server/routes.py: TemplateRepo.list_all()
    └── 从 SQLite 加载所有已注册模板（gallery）
    │
    ▼
algorithm/matcher.py: match()
    ├── probe vs 每个 gallery 模板
    ├── 环形方向距离 + shift matching
    ├── 掩码归一化均值距离
    └── 取最小距离
    │
    ▼
server/routes.py: 判决
    ├── min_dist < threshold (0.4284) → 匹配成功
    └── min_dist >= threshold          → 匹配失败
    │
    ├───────────────────────────────────────────┐
    │ 匹配成功                                   │ 匹配失败
    ▼                                           ▼
bridge.unlock(3000)                     bridge.indicate(False)
    │                                           │
    ▼                                           ▼
serial.write("UNLOCK 3000\n")           serial.write("FAIL\n")
    │                                           │
    ▼                                           ▼
bridge.indicate(True)                   STM32: 红灯亮 + 蜂鸣器双响
    │
    ▼
serial.write("OK\n")
    │
    ▼
STM32: 电磁锁开 3 秒 + 绿灯亮 + 蜂鸣器单响
    │
    ▼
storage/repository.py: LogRepo.add()
    └── SQLite: access_logs 表（user_id, distance, matched, timestamp）
    │
    ▼
返回 {ok: true, matched: true/false, user_name, distance, confidence}
```

### 3.3 视频预览流程

```
frontend: <img src="/video_feed">
    │
    ▼
server/stream.py: generate_frames()
    ├── camera.read() 获取帧
    ├── cv2.imencode(".jpg") 压缩
    └── yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + bytes
    │
    ▼
浏览器 MJPEG 渲染（持续流式传输）
```

---

## 4. 串口协议（PC → STM32）

**物理层**：USB 串口，115200 波特率，8N1

**协议层**：ASCII 行协议，每条命令以 `\n` 结尾

| 方向 | 命令 | 含义 | STM32 响应 |
|------|------|------|-----------|
| PC → STM32 | `UNLOCK <ms>\n` | 开锁指定毫秒 | 无 |
| PC → STM32 | `OK\n` | 验证成功 | 绿灯 + 蜂鸣器单响 |
| PC → STM32 | `FAIL\n` | 验证失败 | 红灯 + 蜂鸣器双响 |
| PC → STM32 | `PING\n` | 心跳检测 | `PONG\n` |

**代码位置**：`hardware/bridge.py` → `SerialBridge` 类

```python
# 核心发送方法
def _send(self, cmd: str) -> None:
    self._ser.write(cmd.encode("utf-8"))

# 开锁
def unlock(self, duration_ms: int) -> None:
    self._send(f"UNLOCK {duration_ms}\n")   # → "UNLOCK 3000\n"

# 指示灯+蜂鸣器
def indicate(self, success: bool) -> None:
    self._send("OK\n" if success else "FAIL\n")
```

---

## 5. 关键配置（config.py）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ROI_SIZE` | 128 | ROI 边长（像素） |
| `GABOR_ORIENTATIONS` | 6 | Gabor 方向数 |
| `MATCH_MAX_SHIFT` | 6 | shift matching 像素范围 |
| `MATCH_THRESHOLD` | 0.4284 | 匹配阈值（标定后） |
| `CAPTURE_FRAMES` | 6 | 多帧选优帧数 |
| `ENROLL_SAMPLES` | 5 | 注册采集帧数 |
| `UNLOCK_MS` | 3000 | 开锁时长（毫秒） |
| `SERIAL_PORT` | "auto" | 串口（auto=自动探测） |
| `SERIAL_BAUD` | 115200 | 波特率 |
| `SERVER_PORT` | 5000 | Flask 端口 |

---

## 6. 启动方式

```bash
# 一键启动（Flask + Vite 同时拉起）
python run.py

# 或分别启动
# 终端 1：Flask 后端
cd server && python -m flask run --port 5000

# 终端 2：Vite 前端
cd frontend && npm run dev
```

**访问地址**：`http://localhost:5173`（Vite 开发服务器，自动代理到 Flask:5000）

---

## 7. 技术栈总览

| 层 | 技术 | 版本 |
|----|------|------|
| 前端 | Vue 3 + Naive UI + Vite + TypeScript | 3.5 / 2.44 / 8.0 / 6.0 |
| 后端 | Flask + NumPy + OpenCV | 3.1 / 2.4 / 4.13 |
| 存储 | SQLite | 内置 |
| 串口 | PySerial | 3.5 |
| 算法 | CompCode（Gabor 竞争编码） | 传统特征，无需训练 |
| 测试 | pytest | 9.0 |
