# 数据目录

本目录除本说明外均不入库（见根 `.gitignore`），协作者按下方步骤自行获取/生成。

| 路径 | 说明 |
|------|------|
| `raw/` | 数据集下载/解压目录（`scripts/download_dataset.py`） |
| `demo/` | 演示合成数据（`scripts/generate_demo_dataset.py` 生成） |
| `cache/` | 编码后的模板缓存（`.pkl`，可删后重算） |
| `reports/` | 标定产物：`calibration.json`、`roc.png`、`det.png` |

## 复现生产级结果（推荐：Tongji 官方 ROI，跨 session）

官方 ROI 是作者裁好对齐的 128×128 掌纹，直接喂给编码/匹配，可复现文献级 EER。

```bash
# 1) 下载（走 Google Drive，需联网；脚本会按需自动装 gdown）
.venv/bin/python scripts/download_dataset.py --dataset tongji-roi   # → data/raw/tongji_roi.rar

# 2) 解压（RAR，需 unar：brew install unar / apt install unar）
unar -o data/raw/palm_roi data/raw/tongji_roi.rar
#    解压后结构：data/raw/palm_roi/tongji_roi/session1, session2（各 6000 张 .bmp）

# 3) 跨 session 标定 + 评测（session1 注册 / session2 验证）
.venv/bin/python scripts/calibrate.py \
    --data-dir data/raw/palm_roi/tongji_roi \
    --protocol cross-session --pre-extracted --max-persons 150
```

输出 `data/reports/calibration.json`（含 EER / Top-1 / 阈值）与 ROC/DET 曲线。
参考结果（150 掌）：**EER ≈ 0.93%，Top-1 ≈ 95%，threshold ≈ 0.43**。
`config.get_match_threshold()` 会自动读取该阈值供服务端使用。

## 快速冒烟（无需下载，合成数据）

```bash
.venv/bin/python scripts/generate_demo_dataset.py
.venv/bin/python scripts/calibrate.py --data-dir data/demo
```

## 备选：Kaggle 整手数据集

```bash
# 需 ~/.kaggle/kaggle.json（chmod 600）
.venv/bin/python scripts/download_dataset.py --dataset palm
.venv/bin/python scripts/calibrate.py --data-dir data/raw/palm
```
