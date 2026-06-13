# 前端串口管理 Implementation Plan

> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为掌纹识别门禁系统添加运行时串口管理能力——前端可切换串口开关、选择 COM 口、修改波特率，参照 SpiRob_Vision 项目的设计。

**Architecture:** SerialBridge 改造为支持 `enabled` 状态和 `reconfigure()` 热重载；后端新增端口枚举和配置更新 API；前端新增串口设置组件，集成到 App.vue 顶栏硬件状态指示旁。串口默认 `enabled=False`（安全），用户通过前端手动启用。

**Tech Stack:** Python pyserial, Flask Blueprint API, Vue 3 Composition API, Naive UI

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `hardware/bridge.py` | Modify | SerialBridge 加 `enabled` 字段 + `reconfigure()` 方法；MockBridge 保留；`create_bridge()` 始终返回 SerialBridge |
| `server/routes.py` | Modify | 新增 `GET /api/serial/ports` 端口枚举 + `POST /api/hardware/config` 串口配置热更新 |
| `server/app.py` | Modify | `create_app()` 中 bridge 初始化逻辑调整（不再传 use_serial 参数） |
| `config.py` | Modify | `SERIAL_ENABLED` 默认值；序列化/持久化串口配置到 `data/reports/serial.json` |
| `frontend/src/api/index.ts` | Modify | 新增 `SerialPortInfo` 类型 + `serialPorts()` / `updateHardwareConfig()` API |
| `frontend/src/components/SerialSettings.vue` | Create | 串口设置组件：启用开关 + 端口下拉框（含刷新）+ 波特率 + 状态指示灯 |
| `frontend/src/App.vue` | Modify | 硬件状态药丸旁加齿轮按钮，点击展开/关闭 SerialSettings 面板 |

---

### Task 1: SerialBridge 改造——支持 enabled + reconfigure

**Files:**
- Modify: `hardware/bridge.py`

- [ ] **Step 1: SerialBridge 加 enabled 字段和 reconfigure 方法**
  - `__init__` 新增 `enabled: bool = False` 参数（替代原来的 `use_serial` 外部判断）
  - 新增 `reconfigure(patch: dict) -> dict` 方法，参照 SpiRob_Vision 的 `SerialComm.reconfigure()`：
    - 接收 `{enabled, port, baudrate}` 部分更新
    - 如果 enabled/port/baudrate 变化，先 `close()` 再 `_open()`
    - 启用但连接失败不抛异常，记录到 `_connect_error`，返回当前状态
    - 关闭时清除错误信息
  - 新增 `close()` 方法（当前缺失，只有 `disconnect` 的概念但无显式 close）
  - `_open()` 方法整合现有 `connect()` 的连接逻辑，失败时记录 `_connect_error` 而非直接 raise
  - `status()` 方法已存在，确认返回值包含 `enabled` 字段

- [ ] **Step 2: MockBridge 保留但简化**
  - `MockBridge.status()` 返回 `enabled: False`（保持不变）
  - `MockBridge` 不需要 `reconfigure()`，它本身就是"无硬件"占位

- [ ] **Step 3: create_bridge() 工厂函数改造**
  - 移除 `use_serial` 参数，始终返回 `SerialBridge(enabled=False)`
  - 启动时默认不连接（enabled=False），由前端/API 运行时启用
  - 保留异常兜底：如果 SerialBridge 构造失败（pyserial 未安装等），降级到 MockBridge

- [ ] **Step 4: 验证**
  - 手动测试：导入 SerialBridge，调 `reconfigure({"enabled": True, "port": "COM3"})`，确认连接/断开行为

---

### Task 2: 后端 API——端口枚举 + 配置更新

**Files:**
- Modify: `server/routes.py`
- Modify: `config.py`

- [ ] **Step 1: config.py 加串口配置持久化**
  - 新增 `_SERIAL_STATE_PATH = BASE_DIR / "data" / "reports" / "serial.json"`
  - 新增 `get_serial_config() -> dict` 函数：读 serial.json，不存在则返回默认值 `{"enabled": False, "port": "auto", "baudrate": 115200}`
  - 新增 `save_serial_config(cfg: dict)` 函数：写入 serial.json
  - 这样串口配置（启用/端口/波特率）在重启后保持

- [ ] **Step 2: routes.py 加 GET /api/serial/ports**
  - 参照 SpiRob_Vision 的 `web/app.py`：
    ```python
    @api.get("/serial/ports")
    def serial_ports():
        from serial.tools import list_ports
        ports = []
        for p in list_ports.comports():
            ports.append({"device": p.device, "description": p.description or "", "hwid": p.hwid or ""})
        ports.sort(key=lambda d: d["device"])
        return _ok(ports)
    ```

- [ ] **Step 3: routes.py 加 POST /api/hardware/config**
  - 接收 JSON body: `{enabled?: bool, port?: str, baudrate?: int}`
  - 调用 `bridge.reconfigure(patch)` 获取新状态
  - 调用 `config.save_serial_config()` 持久化
  - 返回 bridge.status()

- [ ] **Step 4: 验证**
  - 启动服务，`curl http://localhost:5000/api/serial/ports` 确认返回 COM 口列表
  - `curl -X POST http://localhost:5000/api/hardware/config -H 'Content-Type: application/json' -d '{"enabled": true, "port": "COM3"}'` 确认返回连接状态

---

### Task 3: app.py 启动逻辑调整

**Files:**
- Modify: `server/app.py`

- [ ] **Step 1: create_app() 改造 bridge 初始化**
  - 移除 `use_serial` 参数
  - 始终调用 `create_bridge()`（返回默认 enabled=False 的 SerialBridge）
  - 启动后从 `config.get_serial_config()` 读取上次的配置，如果 `enabled=True` 则调用 `bridge.reconfigure()` 自动重连
  - 这样重启服务后如果之前启用了串口，会自动尝试重连

- [ ] **Step 2: 验证**
  - 启动服务，确认 `/api/health` 返回 `hardware.enabled: false`（默认状态）
  - 通过 API 启用串口后，确认 health 返回 `enabled: true`

---

### Task 4: 前端 API 层——类型 + 接口调用

**Files:**
- Modify: `frontend/src/api/index.ts`

- [ ] **Step 1: 新增类型定义**
  ```typescript
  export interface SerialPortInfo {
    device: string
    description: string
    hwid: string
  }

  export interface HardwareConfig {
    enabled?: boolean
    port?: string
    baudrate?: number
  }
  ```

- [ ] **Step 2: 新增 API 调用**
  ```typescript
  serialPorts() {
    return request<SerialPortInfo[]>('/api/serial/ports')
  },
  updateHardwareConfig(config: HardwareConfig) {
    return request<HardwareStatus>('/api/hardware/config', {
      method: 'POST',
      body: JSON.stringify(config),
    })
  },
  ```

---

### Task 5: 前端 SerialSettings 组件

**Files:**
- Create: `frontend/src/components/SerialSettings.vue`

- [ ] **Step 1: 组件结构设计**
  - Props: `hardwareStatus: HardwareStatus`（从 App.vue 传入当前状态）
  - Emits: `update`（配置变更后通知父组件刷新状态）
  - 模板参照 SpiRob_Vision 的 ParamPanel.vue 串口部分：
    - 启用串口复选框
    - 连接状态指示灯（三态：灰/绿/红，带 pulse 动画）
    - 端口下拉框 + 刷新按钮
    - 波特率数字输入框
  - 样式遵循项目现有设计语言（圆角药丸、毛玻璃、CSS 变量）

- [ ] **Step 2: 交互逻辑**
  - `onMounted`: 调 `api.serialPorts()` 加载端口列表
  - 启用开关切换：调 `api.updateHardwareConfig({enabled: !current})`，成功后 emit `update`
  - 端口切换：调 `api.updateHardwareConfig({port: selected})`，成功后 emit `update`
  - 波特率修改：调 `api.updateHardwareConfig({baudrate: value})`，成功后 emit `update`
  - 刷新按钮：重新调 `api.serialPorts()` 更新端口列表
  - 端口列表合并逻辑：当前配置的端口即使未检测到也显示（标注"未检测到设备"）

- [ ] **Step 3: 样式实现**
  - 面板容器：毛玻璃背景，圆角，边框，与 topbar 风格一致
  - 指示灯：小圆点 + 颜色 + pulse 动画（参照 App.vue 的 hw-dot 样式）
  - 下拉框/输入框：参照 SpiRob_Vision 的 select/input 样式，使用项目 CSS 变量

---

### Task 6: App.vue 集成——状态药丸旁加设置入口

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 引入 SerialSettings 组件**
  - import SerialSettings
  - 新增 `showSerialSettings` ref 控制面板展开/收起
  - 硬件状态药丸旁加一个小齿轮按钮（点击切换 showSerialSettings）

- [ ] **Step 2: 面板渲染**
  - 在 topbar 下方用条件渲染 `<SerialSettings>` 面板
  - 面板带收起动画（transition）
  - SerialSettings 的 `update` 事件触发 `fetchHealth()` 刷新状态

- [ ] **Step 3: 状态同步**
  - 将 `hardware` ref 作为 prop 传给 SerialSettings
  - SerialSettings 内部操作后，App.vue 的 `fetchHealth()` 自动更新顶部药丸状态

- [ ] **Step 4: 验证**
  - 手动测试完整流程：点击齿轮 → 展开面板 → 勾选启用 → 选择端口 → 确认顶部药丸变绿
  - 确认刷新页面后串口配置保持（持久化生效）

---

## Verification Checklist

- [ ] 默认启动：health 返回 `enabled: false`，前端显示"硬件未启用"（灰色）
- [ ] 前端启用串口：勾选 → 选端口 → 药丸变绿"已连接 COMx"
- [ ] 端口不存在/被占用：药丸变红显示错误信息
- [ ] 重启服务：上次启用的串口自动重连
- [ ] 端口刷新：拔插 USB 后点刷新能看到新端口
- [ ] 串口开关关闭：药丸回到灰色"硬件未启用"
