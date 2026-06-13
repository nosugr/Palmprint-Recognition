"""全局配置项。集中存放阈值、ROI、串口等参数（见 docs/INTERFACE_CONTRACT.md 契约 D）。"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 数据库
DB_PATH = BASE_DIR / "palmprint.db"

# 算法 / 匹配
ROI_SIZE = 128                 # ROI 边长（正方形），性能不足可降到 64
TEMPLATE_VERSION = "compcode-v3"  # v3: Zhang 指缝坐标系 ROI + 均值角度距离 + 可靠性掩码
GABOR_ORIENTATIONS = 6         # Gabor 方向数（0/30/60/90/120/150 度）
MATCH_MAX_SHIFT = 6            # 匹配时的最大平移像素（shift matching）
MATCH_MIN_OVERLAP_FRAC = 0.20  # 两模板有效区重叠低于该比例则判为不可信
COMPCODE_RELIABILITY_Q = 0.25  # 竞争强度低于该分位的像素判为方向不可靠并屏蔽

# 采集硬化：单次采集抓多帧，挑 ROI 质量最高的一帧，降低实时配准失败率
CAPTURE_FRAMES = 6             # 每次注册/验证抓取的候选帧数
CAPTURE_INTERVAL_MS = 60       # 候选帧之间的间隔（毫秒）
VERIFY_PROBE_FRAMES = 3        # 验证时参与比对的候选帧数（质量最高的前 N 帧，多帧融合取最小距离）
MATCH_THRESHOLD = 0.40         # 默认值；若存在标定结果则 get_match_threshold() 优先读取

# 固定 ROI 框（对着定位槽标定；设置后跳过自动分割）
ROI_BOX: tuple[int, int, int, int] | None = None  # (x, y, w, h) 像素

# 自动掌纹 ROI（Zhang 方案）：由两指缝关键点 X1/X2 建坐标系裁方形 ROI。
# 边长 = ROI_PALM_SCALE × |X1X2|；ROI 上沿距指缝线 = ROI_PALM_OFFSET × |X1X2|（向掌心）。
ROI_PALM_SCALE = 1.20
ROI_PALM_OFFSET = 0.40

# 掌纹识别引导框：检测/轮廓只在此正方形区域内进行，排除框外的人脸等干扰。
# 必须与前端 CameraView.vue 的 .guide 几何严格一致（见 docs 计划书）。
ROI_GUIDE_CX = 0.5     # 框中心 x（占画面宽比例）
ROI_GUIDE_CY = 0.5     # 框中心 y（占画面高比例）
ROI_GUIDE_SIDE = 0.58  # 正方形边长 = ROI_GUIDE_SIDE × 画面宽（像素）

# 非手掌排除：防止圆/拳头/脸/杯子等占满画面的凸物体被误判为"位置良好"。
# solidity = 轮廓面积 / 凸包面积；张开五指有深指缝 ≈ 0.6–0.75，凸物体 ≈ 1.0。
ROI_MAX_SOLIDITY = 0.90       # 高于该值判为"未张开五指/非手掌"，拒识（放宽以容忍手指张开不足）
# 指缝深度：谷点到掌心的距离须 < 该比例 × 相邻指尖距离，否则视为无真实指缝（圆块谷≈尖）
ROI_MAX_VALLEY_RATIO = 0.95       # 0.92 → 0.95，放宽指缝深度门
ROI_FINGER_MIN_TIPS = 3           # 最少指尖数（原硬编码 4，降至 3 允许无名/小指并拢）
ROI_FINGER_MERGE_SEP = 0.30       # 双峰合并角距 rad（原硬编码 0.22，放宽以容忍光照不均）

# 预处理：有效像素亮度范围（超出视为无效）
ROI_INTENSITY_LOW = 20
ROI_INTENSITY_HIGH = 235

# Gabor 滤波参数（CompCode，128×128 掌纹；在 Tongji 跨 session 上标定得到）
GABOR_KSIZE = 35
GABOR_SIGMA = 4.5
GABOR_LAMBDA = 9.0
GABOR_GAMMA = 0.8

# 注册
ENROLL_SAMPLES = 5             # 注册时采集的帧数（多模板存储）
MAX_TEMPLATES_PER_HAND = 5     # 每用户每只手保留的模板上限（新旧合并按质量取前 N）

# 硬件 / 串口（PC ↔ STM32）
UNLOCK_MS = 3000               # 开锁时长（毫秒）
SERIAL_PORT = "auto"           # STM32 串口设备，auto=自动探测
SERIAL_BAUD = 115200           # 波特率（与嵌入式组约定）

# 摄像头
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))  # 初始摄像头设备号（无持久化时的默认）
CAMERA_PROBE_COUNT = 6        # 探测的索引范围：0 .. CAMERA_PROBE_COUNT-1

# 服务
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.environ.get("SERVER_PORT", "5000"))

_CALIBRATION_PATH = BASE_DIR / "data" / "reports" / "calibration.json"
_CAMERA_STATE_PATH = BASE_DIR / "data" / "reports" / "camera.json"


def get_default_camera_index() -> int:
    """启动时使用的摄像头索引：优先读上次在界面里选定并持久化的值。"""
    if _CAMERA_STATE_PATH.exists():
        import json

        try:
            data = json.loads(_CAMERA_STATE_PATH.read_text(encoding="utf-8"))
            return int(data["index"])
        except (ValueError, KeyError, OSError):
            pass
    return CAMERA_INDEX


def save_default_camera_index(index: int) -> None:
    """把当前选定的摄像头索引持久化，供下次启动作为默认。"""
    import json

    _CAMERA_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CAMERA_STATE_PATH.write_text(json.dumps({"index": int(index)}), encoding="utf-8")


def get_match_threshold() -> float:
    """优先使用 scripts/calibrate.py 产出的标定阈值。"""
    if _CALIBRATION_PATH.exists():
        import json

        data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
        return float(data["threshold"])
    return MATCH_THRESHOLD


_HARDWARE_STATE_PATH = BASE_DIR / "data" / "reports" / "hardware.json"


def get_serial_enabled() -> bool:
    """读取串口开关，默认 True"""
    if _HARDWARE_STATE_PATH.exists():
        import json

        try:
            data = json.loads(_HARDWARE_STATE_PATH.read_text(encoding="utf-8"))
            return bool(data.get("serial_enabled", True))
        except (ValueError, KeyError, OSError):
            pass
    return True


def save_serial_enabled(enabled: bool) -> None:
    """保存串口开关"""
    import json

    _HARDWARE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HARDWARE_STATE_PATH.write_text(json.dumps({"serial_enabled": enabled}), encoding="utf-8")
