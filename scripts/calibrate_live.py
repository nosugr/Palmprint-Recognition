"""实时场景阈值标定工具：从摄像头采集多人掌纹 → 计算 EER → 写入 calibration.json。

用法：
  .venv\Scripts\python scripts\calibrate_live.py
  .venv\Scripts\python scripts\calibrate_live.py --persons 5 --samples 4 --camera 1

流程：
  1. 逐个提示受试者把手掌放入引导框，按空格采集
  2. 每人采集 N 帧掌纹模板
  3. 全部采集完毕后，计算 genuine / impostor 距离分布
  4. 标定最优阈值（EER 交点）
  5. 写入 data/reports/calibration.json（覆盖旧值）

最少需要 3 人才能计算 EER；建议 5 人以上。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

import config
from algorithm.encode import encode
from algorithm.evaluation import compute_eer, plot_det, plot_roc
from algorithm.preprocess import finalize_patch, to_gray
from algorithm.roi import extract_palm_roi_ex
from algorithm.template import PalmTemplate, mask_array
from hardware.camera import WebcamCamera


def _capture_single(camera: WebcamCamera) -> tuple[PalmTemplate, np.ndarray] | None:
    """从摄像头抓一帧，提取 ROI 并编码。成功返回 (template, frame)，失败返回 None。"""
    for _ in range(config.CAPTURE_FRAMES):
        frame = camera.read()
        if frame is None:
            continue
        res = extract_palm_roi_ex(to_gray(frame), bgr=frame)
        if res.ok:
            roi, valid_mask = finalize_patch(res.roi, res.mask)
            template = encode(roi, valid_mask)
            return template, frame
        time.sleep(config.CAPTURE_INTERVAL_MS / 1000.0)
    return None


def _draw_guide(frame: np.ndarray) -> np.ndarray:
    """在帧上画引导框（与前端 CameraView 的引导框一致）。"""
    h, w = frame.shape[:2]
    from algorithm.roi import guide_box
    gx0, gy0, gx1, gy1 = guide_box(w, h)
    cv2.rectangle(frame, (gx0, gy0), (gx1, gy1), (180, 180, 180), 2)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="实时场景掌纹阈值标定")
    parser.add_argument("--persons", type=int, default=5, help="受试者人数（最少 3）")
    parser.add_argument("--samples", type=int, default=4, help="每人采集帧数")
    parser.add_argument("--camera", type=int, default=0, help="摄像头设备号")
    parser.add_argument("--reports-dir", type=Path, default=Path("data/reports"))
    args = parser.parse_args()

    if args.persons < 3:
        print("错误：至少需要 3 人才能计算 EER")
        sys.exit(1)

    camera = WebcamCamera(args.camera)
    if not camera.is_open():
        print(f"错误：无法打开摄像头 {args.camera}")
        sys.exit(1)

    print(f"实时标定：{args.persons} 人 × {args.samples} 帧")
    print("操作提示：")
    print("  - 把手掌放入画面中的引导框内，五指张开")
    print("  - 按 [空格] 采集当前帧")
    print("  - 按 [q] 放弃当前人/退出")
    print()

    # gallery[person_id] = [PalmTemplate, ...]
    gallery: dict[int, list[PalmTemplate]] = {}
    window_name = "Palmprint Calibration (press SPACE to capture, Q to quit)"

    for person_id in range(args.persons):
        print(f"--- 受试者 {person_id + 1}/{args.persons} ---")
        templates: list[PalmTemplate] = []

        while len(templates) < args.samples:
            frame = camera.read()
            if frame is None:
                continue

            display = _draw_guide(frame.copy())
            count_text = f"Person {person_id + 1}  [{len(templates)}/{args.samples}]"
            cv2.putText(display, count_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(display, "SPACE=capture  Q=skip/quit", (10, display.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            cv2.imshow(window_name, display)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord(" "):
                print(f"  采集第 {len(templates) + 1} 帧...", end=" ", flush=True)
                result = _capture_single(camera)
                if result is not None:
                    tmpl, _ = result
                    templates.append(tmpl)
                    q = float(mask_array(tmpl).mean())
                    print(f"成功 (质量 {q:.3f})")
                else:
                    print("失败（未检测到手掌，请重新放手）")

        if len(templates) >= 2:
            gallery[person_id] = templates
            print(f"  受试者 {person_id + 1}：采集 {len(templates)} 帧 ✓")
        else:
            print(f"  受试者 {person_id + 1}：不足 2 帧，跳过")

    camera.release()
    cv2.destroyAllWindows()

    valid_persons = [pid for pid, tmpls in gallery.items() if len(tmpls) >= 2]
    if len(valid_persons) < 3:
        print(f"\n错误：有效受试者 {len(valid_persons)} 人，不足 3 人，无法标定")
        sys.exit(1)

    print(f"\n有效受试者：{len(valid_persons)} 人")
    for pid in valid_persons:
        print(f"  受试者 {pid + 1}: {len(gallery[pid])} 帧")

    # 计算 genuine / impostor 距离
    print("\n计算距离分布...")
    genuine: list[float] = []
    impostor: list[float] = []

    for pid in valid_persons:
        tmpls = gallery[pid]
        # genuine：同人所有两两组合
        for a, b in combinations(tmpls, 2):
            d = match_distance(a, b)
            genuine.append(d)

    # impostor：不同人的各取第一帧两两比对
    first_frames = [(pid, gallery[pid][0]) for pid in valid_persons]
    for i in range(len(first_frames)):
        for j in range(i + 1, len(first_frames)):
            d = match_distance(first_frames[i][1], first_frames[j][1])
            impostor.append(d)

    gen = np.array(genuine, dtype=np.float64)
    imp = np.array(impostor, dtype=np.float64)

    print(f"  genuine pairs: {len(gen)}")
    print(f"  impostor pairs: {len(imp)}")
    print(f"  genuine 均值: {gen.mean():.4f}  std: {gen.std():.4f}")
    print(f"  impostor 均值: {imp.mean():.4f}  std: {imp.std():.4f}")

    if len(gen) < 5 or len(imp) < 5:
        print("\n警告：样本量太少，标定结果可能不准确")
        print("建议增加人数或每人的采集帧数")

    # 计算 EER
    result = compute_eer(gen, imp)

    reports = args.reports_dir
    reports.mkdir(parents=True, exist_ok=True)
    roc_path = plot_roc(result, reports / "roc.png", title="ROC (live calibration)")
    det_path = plot_det(result, reports / "det.png", title="DET (live calibration)")

    calibration = {
        "dataset": "live-camera",
        "protocol": "live",
        "pre_extracted": False,
        "persons": len(valid_persons),
        "templates": sum(len(gallery[pid]) for pid in valid_persons),
        "genuine_pairs": int(len(gen)),
        "impostor_pairs": int(len(imp)),
        "eer": round(result.eer, 4),
        "threshold": round(result.threshold, 4),
        "far_at_eer": round(result.far_at_eer, 4),
        "frr_at_eer": round(result.frr_at_eer, 4),
        "roc_plot": str(roc_path.resolve()),
        "det_plot": str(det_path.resolve()),
    }
    cal_path = reports / "calibration.json"
    cal_path.write_text(json.dumps(calibration, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 40)
    print("  实时标定结果")
    print("=" * 40)
    print(f"  受试者     : {len(valid_persons)} 人")
    print(f"  EER        : {result.eer:.2%}")
    print(f"  阈值       : {result.threshold:.4f}  ← 已写入 calibration.json")
    print(f"  FAR@EER    : {result.far_at_eer:.4f}")
    print(f"  FRR@EER    : {result.frr_at_eer:.4f}")
    print(f"  ROC        : {roc_path}")
    print(f"  报告       : {cal_path}")
    print()
    print("下次启动系统时将自动使用新阈值。")


if __name__ == "__main__":
    from algorithm.matcher import match_distance  # 延迟导入避免循环
    main()
