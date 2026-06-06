# AGENTS.md

掌纹识别门禁系统 · 课程设计。本文件给接手的人或 AI Agent 快速建立上下文。

## 这是什么

基于掌纹识别的门禁系统课设。掌纹识别成功后驱动电磁锁开锁，配 Web 管理界面（注册/验证/日志）。

- 平台：**PC/笔记本**（跑视觉算法 + Flask + Web）+ **STM32**（跑门锁固件，嵌入式组负责）。
- 二者通过**串口**通信。本仓库只负责软件侧（PC 那一半）。

技术栈：

- 算法/后端：Python + OpenCV + NumPy + Flask + SQLite。
- 前端：**Vite + Vue 3 + Naive UI**（独立 `frontend/` 工程，Node ≥ 22）。dev 用 Vite proxy 接 Flask，prod 由 Flask 托管 `dist/`。
- 硬件桥接：`pyserial` 走串口，PC 开发期用 Mock。

## 必读文档（按顺序）

1. `DESIGN.md` — 课设总计划书（背景、硬件、分工、时间线）。
2. `docs/INTERFACE_CONTRACT.md` — **边界契约**，跨模块/跨团队的接口约定。改实现前先读它，别破坏契约。
3. `docs/SOFTWARE_DESIGN.md` — 软件部分的详细实现蓝图（各层设计、关键决策、测试、开发顺序）。

## 职责边界

- ✅ 本仓库（软件组）：视觉算法、Flask 后端、SQLite、Web 前端、串口命令发送侧。
- ❌ 不在本仓库：STM32 固件、电磁锁/LED/蜂鸣器电路（嵌入式组负责，按 `INTERFACE_CONTRACT.md` 契约 A 对接）。

## 核心原则

1. `algorithm/` 层零硬件依赖，可在任何机器单测。
2. 摄像头与硬件都走抽象接口，PC 开发期用 Mock，最后才接真硬件。
3. 依赖方向严格自下而上：`hardware → algorithm → storage → server → frontend`，算法层永不 import Flask/hardware。

## 当前状态

设计阶段。代码尚未开始；契约与设计文档已就绪。开发顺序见 `docs/SOFTWARE_DESIGN.md` 第 6 节（S0→S6）。

## 待确认的开放决策（见 SOFTWARE_DESIGN.md）

- 特征编码：CompCode（推荐）vs 原 PalmCode。
- 测试覆盖程度（建议 `algorithm/` 配单元测试）。
- 串口协议细节（波特率/响应帧等，与嵌入式组敲定）。
