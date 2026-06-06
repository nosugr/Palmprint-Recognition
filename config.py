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
MATCH_THRESHOLD = 0.40         # 默认值；若存在标定结果则 get_match_threshold() 优先读取

# 固定 ROI 框（对着定位槽标定；设置后跳过自动分割）
ROI_BOX: tuple[int, int, int, int] | None = None  # (x, y, w, h) 像素

# 自动掌纹 ROI（Zhang 方案）：由两指缝关键点 X1/X2 建坐标系裁方形 ROI。
# 边长 = ROI_PALM_SCALE × |X1X2|；ROI 上沿距指缝线 = ROI_PALM_OFFSET × |X1X2|（向掌心）。
ROI_PALM_SCALE = 1.20
ROI_PALM_OFFSET = 0.40

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

# 硬件 / 串口（PC ↔ STM32）
UNLOCK_MS = 3000               # 开锁时长（毫秒）
SERIAL_PORT = "auto"           # STM32 串口设备，auto=自动探测
SERIAL_BAUD = 115200           # 波特率（与嵌入式组约定）

# 服务
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.environ.get("SERVER_PORT", "5000"))

_CALIBRATION_PATH = BASE_DIR / "data" / "reports" / "calibration.json"


def get_match_threshold() -> float:
    """优先使用 scripts/calibrate.py 产出的标定阈值。"""
    if _CALIBRATION_PATH.exists():
        import json

        data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
        return float(data["threshold"])
    return MATCH_THRESHOLD
