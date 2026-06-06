# 软件详细设计 · 掌纹识别门禁系统

> 本文是软件部分的实现蓝图，面向实现者（人或接手的 Agent）。配合 `INTERFACE_CONTRACT.md`（边界契约）与根目录 `DESIGN.md`（课设计划书）一起读。
>
> 阅读顺序建议：先看 `INTERFACE_CONTRACT.md` 把边界吃透，再看本文了解每层怎么实现。

---

## 1. 范围与前提

| 项 | 结论 |
|----|------|
| 平台 | PC/笔记本跑视觉+Web；STM32 跑门锁固件（嵌入式组负责，不在本仓库） |
| 软件组负责 | 视觉算法、Flask 后端、SQLite、Web 前端、串口命令发送侧 |
| 采集方式 | **物理定位槽 + 固定 ROI 框**（已定，决定 ROI 策略走简单路线） |
| 开发方式 | **PC 优先**：摄像头与硬件均抽象，PC 上用 mock 跑通全流程，最后接真硬件 |
| 补光 | 假设可见光白光（NIR 未采用）。若改 NIR 需重新评估预处理 |

### 关键设计原则

1. **算法层零硬件依赖**：`algorithm/` 只吃 numpy 数组、吐 `PalmTemplate`，可在任何机器上单测，不碰摄像头/串口/Flask。
2. **硬件可插拔**：摄像头、门锁都走抽象接口，`Mock` 与真实实现一行切换。
3. **先跑公开数据集，再上现场**：用 Kaggle 数据把算法和 EER 调好，再用自录数据演示。

---

## 2. 目录结构

```
biometrics/
├── DESIGN.md                  # 课设计划书（已有）
├── AGENTS.md                  # 接手入口
├── docs/
│   ├── INTERFACE_CONTRACT.md  # 边界契约
│   └── SOFTWARE_DESIGN.md     # 本文
├── requirements.txt
├── config.py                  # 配置项（阈值、ROI 尺寸、串口等）
├── algorithm/                 # 【S1】纯算法层，零硬件依赖
│   ├── preprocess.py          #   灰度/均衡/ROI/归一化
│   ├── encode.py              #   Gabor 滤波 + 编码 → PalmTemplate
│   ├── matcher.py             #   掩码汉明距离 + shift matching
│   ├── template.py            #   PalmTemplate 数据类 + 序列化
│   └── evaluation.py          #   EER / FAR / FRR / 曲线绘制
├── storage/                   # 【S2】持久化层
│   ├── db.py                  #   SQLite 连接与建表
│   └── repository.py          #   users/templates/logs 的增删查
├── hardware/                  # 【S5】硬件桥接层（受平台变更影响的唯一一层）
│   ├── bridge.py              #   HardwareBridge ABC + MockBridge + SerialBridge
│   └── camera.py              #   Camera ABC + WebcamCamera + FolderCamera(mock)
├── server/                    # 【S3】Flask 编排层（后端服务）
│   ├── app.py                 #   应用工厂 + 依赖注入
│   ├── routes.py              #   契约 C 的 API 实现
│   └── stream.py              #   MJPEG 推流
├── frontend/                  # 【S4】前端：Vite + Vue 3 + Naive UI（独立 npm 工程）
│   ├── package.json
│   ├── vite.config.ts         #   dev proxy: /api、/video_feed → :5000；按需自动导入 Naive UI
│   ├── index.html
│   ├── src/
│   │   ├── main.ts            #   createApp + NConfigProvider/NMessageProvider 包裹
│   │   ├── App.vue            #   外层布局 + tab 切换
│   │   ├── api/index.ts       #   封装 fetch，对接契约 C
│   │   └── views/
│   │       ├── Enroll.vue     #   注册
│   │       ├── Verify.vue     #   实时验证（<img src="/video_feed">）
│   │       └── Logs.vue       #   识别日志（n-data-table）
│   └── dist/                  #   构建产物（生产期由 Flask 托管）
├── scripts/
│   ├── calibrate.py           #   在数据集上跑 EER、确定阈值
│   └── collect.py             #   自录数据采集小工具
└── tests/                     # 【S1 单测】
    ├── test_preprocess.py
    ├── test_encode.py
    └── test_matcher.py
```

---

## 3. 各层详细设计

### S1 · 算法核心层（重头，最该花时间）

#### S1.1 预处理 `preprocess.py`

流水线：`原图 → 灰度 → CLAHE 直方图均衡 → 固定 ROI 裁剪 → resize 128×128 → 归一化`

- **固定 ROI 框**：因采用物理定位槽，手掌位置被强约束，直接取画面中心预设矩形即可。ROI 框的位置/大小作为配置常量，调试期对着定位槽标定一次。
  - 这是 1A 决策的核心收益：**跳过了无接触掌纹最难的指缝谷点对齐问题**。
- **CLAHE**（`cv2.createCLAHE`）比全局直方图均衡更抗局部光照不均，掌纹场景更稳。
- 输出：`uint8` 的 `128×128` 灰度图。
- **有效区 mask**：同时产出一张 mask，标记过暗/过曝/边缘无效像素（后续编码与匹配只用有效位）。

#### S1.2 特征编码 `encode.py` —— ⚠️ 需你拍板的决策点

对 ROI 做多方向 Gabor 滤波后编码。有两种主流方案，对外都产出 `PalmTemplate`，但**鲁棒性和位数不同**：

| 方案 | 做法 | bits/pixel | 评价 |
|------|------|-----------|------|
| **PalmCode**（DESIGN.md 原文「取符号」） | 单组/逐方向 Gabor，对实部虚部取符号 | 2 | 实现最简单，但对方向纹理区分弱 |
| **Competitive Code（CompCode）** | 6 方向 Gabor，取响应最强（最负）的**方向索引** | 3（编码 6 方向）| 掌纹识别业界更主流、区分度更高、抗光照更好 |

> **我的建议**：用 **CompCode**。它正是「6 方向 Gabor」最自然的归宿，区分度明显优于纯取符号，EER 更容易压到 10% 以下，且实现复杂度只比 PalmCode 高一点。匹配时用「角度距离」而非普通异或，我会在 `matcher.py` 里配套实现。
>
> DESIGN.md 写的是「取符号」，所以这是与原计划的一处偏离，**需要你确认走 CompCode 还是保持原 PalmCode**。无论选哪个，`PalmTemplate` 容器和下游都不变。

- Gabor 核：`cv2.getGaborKernel`，6 个方向 `θ ∈ {0, 30, 60, 90, 120, 150}°`，其余参数（波长 λ、带宽 σ、γ）实现时按经验值起步并在标定阶段微调。
- 编码结果用 `np.packbits` 压成 `bytes` 存入 `PalmTemplate.code`，mask 同样打包。

#### S1.3 匹配 `matcher.py`

- **掩码归一化汉明距离**：只在两模板 mask 同时有效的位上计算不同位比例，`distance ∈ [0,1]`。
- **Shift matching（必须有，DESIGN.md 遗漏）**：即便有定位槽仍有几像素偏移。把其中一个 code 在 `±max_shift`（默认 3）像素范围内平移，取所有偏移下的最小距离。不加这一步，同人距离会系统性偏大，EER 崩。
- 若用 CompCode，距离用方向索引的**角度差**（环形距离）而非位异或。
- 判决：`min_distance < MATCH_THRESHOLD` → 命中。多模板时取与该用户所有模板的最小距离。

#### S1.4 性能评估 `evaluation.py`

- 输入：一批带标签的 `PalmTemplate`（来自公开数据集）。
- 生成所有同人对（genuine）与不同人对（impostor）的距离分布。
- 遍历阈值算 FAR/FRR，求 **EER**（FAR=FRR 交点），绘制 ROC/DET 曲线（matplotlib）。
- 输出阈值建议值，写入 `config.MATCH_THRESHOLD`。
- 这一步产出答辩用的核心图表，**完全在 PC + 公开数据集上完成，不依赖任何硬件**。

---

### S2 · 持久化层 `storage/`

- `db.py`：建表（契约 D 的 schema）、连接管理、`PRAGMA foreign_keys=ON`。
- `repository.py`：`add_user / list_users / delete_user / add_template / load_all_templates / add_log / list_logs`。
- **⚠️ 对 DESIGN.md「5 张取均值特征」的纠正**：二进制编码（PalmCode/CompCode）**不能做算术平均**——对 bit 求均值没有几何意义。正确做法二选一：
  1. **多模板**（推荐）：5 张各存一条 template，匹配时取最小距离。简单、鲁棒、可解释。
  2. **逐位多数表决**：对 5 张同位置的 bit 取多数。可减小存储，但要小心 mask。
  - 我倾向方案 1（schema 已按「一个用户多条模板」设计）。这是与原计划的一处技术纠正，已在契约 D 注明。

---

### S3 · 服务层 `server/`（Flask 编排）

- `app.py`：应用工厂，启动时注入依赖——`Camera` 与 `HardwareBridge` 的具体实现（PC 用 Mock/Webcam，现场用真实）。
- `routes.py`：实现契约 C 的全部 API。`/api/verify` 流程：取当前帧 → 预处理 → 编码 → 与库内模板匹配 → 写 log → 命中则 `bridge.unlock()+indicate(True)`，否则 `indicate(False)`。
- `stream.py`：MJPEG 推流，已核实当前标准写法：

```python
def gen_frames(camera):
    while True:
        frame = camera.read()                       # BGR ndarray
        ok, buf = cv2.imencode('.jpg', frame)
        if not ok:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
# app.run(..., threaded=True) 必须开 threaded，否则推流会阻塞其它请求
```

---

### S4 · 前端 `frontend/`（Vite + Vue 3 + Naive UI）

技术栈（已核实当前版本）：

| 项 | 版本/说明 |
|----|----------|
| 构建 | Vite 6/7 |
| 框架 | Vue 3（3.5+），`<script setup>` SFC |
| UI 库 | Naive UI 2.x（无需 CSS loader，TS 友好） |
| 自动导入 | `unplugin-vue-components` + `NaiveUiResolver`、`unplugin-auto-import` |
| Node | ≥ 22 |

页面（`App.vue` 用 `n-tabs` 切三个 view）：

- **注册 `Enroll.vue`**：`n-input` 输姓名 → 调 `/api/enroll` → `n-progress` 显示采集进度、`n-message` 反馈质量。
- **验证 `Verify.vue`**：`<img src="/video_feed">` 显示实时画面 + `n-button` 触发 `/api/verify` → 用 `n-result`/`n-tag` 展示命中用户、相似度、阈值，绿/红反馈。
- **日志 `Logs.vue`**：`n-data-table` 展示 `/api/logs`。

**前后端对接方式**（我定的默认，可改）：

- **开发期**：`vite dev`（:5173）热更新；`vite.config.ts` 配 `server.proxy` 把 `/api` 与 `/video_feed` 转发到 Flask（:5000）。前端只管 `/api/*`，不写死后端地址，**无 CORS 问题**。
- **生产/演示期**：`npm run build` → `frontend/dist/`，由 Flask 静态托管（`app.py` 挂载 dist，契约 C 的 `/` 返回 `index.html`）。一个进程对外，部署简单。

Naive UI 按需自动导入（写进 `vite.config.ts`，已核实为当前推荐写法）：

```ts
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({ imports: ['vue', { 'naive-ui': ['useMessage', 'useDialog'] }] }),
    Components({ resolvers: [NaiveUiResolver()] }),
  ],
  server: { proxy: { '/api': 'http://localhost:5000', '/video_feed': 'http://localhost:5000' } },
})
```

> 相比原「极简单页」方案复杂度上升，但你已选定该栈；为控制 scope，组件库统一用 Naive UI 现成组件，不自造样式。

---

### S5 · 硬件桥接层 `hardware/`（平台变更唯一受影响处）

- `bridge.py`：契约 A 的 `HardwareBridge` ABC + `MockBridge`（打印日志）+ `SerialBridge`（`pyserial`，按串口行协议编码）。
- `camera.py`：`Camera` ABC + `WebcamCamera`（`cv2.VideoCapture(0)`）+ `FolderCamera`（读图片目录，供无摄像头时跑流程/测试）。
- STM32 固件由嵌入式组实现，只需匹配契约 A.2 的串口协议。软件侧不关心 STM32 内部。

---

## 4. 关键设计决策与取舍（汇总，供审阅）

| # | 决策 | 取舍理由 | 状态 |
|---|------|----------|------|
| 1 | 固定 ROI 框（靠定位槽）而非谷点对齐 | 一周一人，把难算法降级为机械约束，最稳 | 已定(1A) |
| 2 | 编码用 CompCode 而非纯取符号 PalmCode | 区分度更高、EER 更易达标 | **待你确认** |
| 3 | 匹配加 shift matching | 修正残余偏移，否则同人距离偏大 | 建议必做 |
| 4 | 编码带 mask，距离只算有效位 | 排除过暗/过曝/边缘干扰 | 建议必做 |
| 5 | 多模板存储而非「均值特征」 | 二进制码不能算术平均 | 建议必做(纠正 DESIGN) |
| 6 | 硬件/摄像头抽象 + Mock | PC 优先开发，解耦 STM32 | 已定(2A) |
| 7 | 前端用 Vite + Vue 3 + Naive UI | 你指定的栈；用现成组件库控制 scope | 已定 |
| 8 | 前端 dev 用 Vite proxy、prod 由 Flask 托管 dist | 兼顾热更新与无 CORS、单进程部署 | 我定的默认，可改 |

---

## 5. 测试策略 —— ⚠️ 需你确认覆盖程度

建议（待你拍板）：

- **`algorithm/`（S1）配单元测试**——它是答辩指标的命根子，值得：
  - `test_preprocess`：固定输入图 → ROI 尺寸/类型断言；mask 正确性。
  - `test_encode`：同一图两次编码结果一致（可复现）；输出 `PalmTemplate` 字段合法。
  - `test_matcher`：构造同人/不同人样例，断言同人距离 < 不同人距离；shift matching 在平移图上能拉低距离。
- **`storage/`**：建表、增删查的轻量集成测试（用临时 SQLite）。
- **`server/` 与 `frontend/`**：手动验证为主（启动服务、点页面、看推流与开锁命令日志）。
- 框架用 `pytest`。

> 请确认：S1 是否按上面做单测？其余层手动验证可否？或者你有不同的覆盖期望？

---

## 6. 开发顺序（映射到课设时间线）

| 步骤 | 内容 | 依赖 | 可独立于硬件 |
|------|------|------|:---:|
| S0 | 骨架 + config + 依赖 + 契约落地 | — | ✅ |
| S1 | 算法核心 + 公开数据集跑通 + EER | S0 | ✅ |
| S2 | SQLite + 注册/查询逻辑 | S1 | ✅ |
| S3 | Flask API + MJPEG（注入 Mock） | S1,S2 | ✅ |
| S4 | 前端三 tab | S3 | ✅ |
| S5 | 接真摄像头 + SerialBridge 联调 STM32 | S3,契约A | ❌ 需硬件 |
| S6 | 自录数据测试 + 性能图 + README | 全部 | 部分 |

> S0–S4 全部可在笔记本上完成（Mock + 公开数据集），只有 S5 需要等 STM32 就绪。这正是 2A 决策带来的最大收益：**软件进度不被硬件卡住。**

---

## 7. 风险（软件侧）

| 风险 | 应对 |
|------|------|
| 固定 ROI 框对不准定位槽 | 调试期对着实物标定 ROI 坐标；定位槽加手掌轮廓引导 |
| CompCode 参数难调、EER 不达标 | 先在干净 Kaggle 数据调参；报告区分「公开数据集指标」与「现场指标」 |
| 串口协议与 STM32 对不齐 | 契约 A.2 提前敲定；`MockBridge` 先行，`SerialBridge` 留协议开关 |
| PC 摄像头帧率/推流卡顿 | 降流分辨率、`threaded=True`、验证按需触发而非每帧匹配 |
