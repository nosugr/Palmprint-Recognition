"""在数据集上标定 CompCode 阈值：编码 → EER → 阈值 → ROC/DET → calibration.json

CompCode 无需训练；本脚本做阈值标定与性能评估。支持两种协议：

- single：单数据集内所有样本两两比对（demo/小数据集）。
- cross-session：session1 注册 / session2 验证（Tongji 官方协议，最诚实的数字）。

示例（Tongji 官方 ROI，跨 session）：
  .venv/bin/python scripts/calibrate.py \
      --data-dir data/raw/palm_roi/tongji_roi \
      --protocol cross-session --pre-extracted --max-persons 600
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / ".matplotlib"))

from algorithm.dataset import (
    discover_cross_session,
    discover_dataset,
    subsample,
)
from algorithm.evaluation import (
    compute_eer,
    cross_session_scores,
    evaluate_identification,
    evaluate_identification_cross_session,
    pairwise_scores,
    plot_det,
    plot_roc,
)
from algorithm.pipeline import cache_path, encode_samples, load_cache, save_cache, write_manifest


def _encode_cached(samples, cache, *, no_cache: bool, pre_extracted: bool):
    pairs = None if no_cache else load_cache(cache)
    if pairs is None:
        t0 = time.perf_counter()
        pairs = encode_samples(samples, pre_extracted=pre_extracted)
        save_cache(pairs, cache)
        print(f"Encoded in {time.perf_counter() - t0:.1f}s (cached → {cache})")
    else:
        print(f"Loaded cache → {cache}")
    return pairs


def _run_single(args, data_dir):
    samples = discover_dataset(data_dir, images_per_identity=args.images_per_identity)
    samples = subsample(samples, max_persons=args.max_persons, max_per_person=args.max_per_person)
    persons = len({s.label for s in samples})
    print(f"Samples: {len(samples)} from {persons} persons")

    pairs = _encode_cached(
        samples, cache_path(data_dir.resolve(), "single"),
        no_cache=args.no_cache, pre_extracted=args.pre_extracted,
    )
    templates = [t for _, t in pairs]
    labels = [s.label_id for s, _ in pairs]

    print("Computing pairwise distances …")
    t0 = time.perf_counter()
    genuine, impostor = pairwise_scores(templates, labels, max_impostor_pairs=args.max_impostor_pairs)
    print(f"  genuine: {len(genuine)}, impostor: {len(impostor)} ({time.perf_counter() - t0:.1f}s)")

    result = compute_eer(genuine, impostor)
    id_result = evaluate_identification(
        list(zip(labels, templates)),
        enroll_per_person=args.enroll_per_person,
        threshold=result.threshold,
    )
    return result, id_result, persons, len(templates)


def _run_cross_session(args, data_dir):
    samples = discover_cross_session(data_dir, images_per_identity=args.images_per_identity)
    if args.max_persons is not None:
        samples = [s for s in samples if s.label_id < args.max_persons]
    persons = len({s.label_id for s in samples})
    print(f"Samples: {len(samples)} from {persons} palms (2 sessions)")

    pairs = _encode_cached(
        samples, cache_path(data_dir.resolve(), "xsession"),
        no_cache=args.no_cache, pre_extracted=args.pre_extracted,
    )
    enroll = [(s.label_id, t) for s, t in pairs if s.session == "session1"]
    probe = [(s.label_id, t) for s, t in pairs if s.session == "session2"]
    print(f"  enroll(session1): {len(enroll)}, probe(session2): {len(probe)}")

    print("Computing cross-session distances …")
    t0 = time.perf_counter()
    genuine, impostor = cross_session_scores(
        enroll, probe, max_impostor_pairs=args.max_impostor_pairs
    )
    print(f"  genuine: {len(genuine)}, impostor: {len(impostor)} ({time.perf_counter() - t0:.1f}s)")

    result = compute_eer(genuine, impostor)
    id_result = evaluate_identification_cross_session(enroll, probe, threshold=result.threshold)
    return result, id_result, persons, len(pairs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate CompCode threshold on palm dataset")
    parser.add_argument("--data-dir", type=Path, default=Path("data/demo"))
    parser.add_argument("--protocol", choices=["single", "cross-session"], default="single")
    parser.add_argument("--pre-extracted", action="store_true",
                        help="输入已是裁好的 ROI（如官方 ROI 数据集），跳过手掌分割")
    parser.add_argument("--max-persons", type=int, default=40)
    parser.add_argument("--max-per-person", type=int, default=4)
    parser.add_argument("--images-per-identity", type=int, default=10,
                        help="无标签时：连续 N 张视为同一掌（Tongji=10）")
    parser.add_argument("--max-impostor-pairs", type=int, default=20000)
    parser.add_argument("--enroll-per-person", type=int, default=2)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--reports-dir", type=Path, default=Path("data/reports"))
    args = parser.parse_args()

    data_dir = args.data_dir
    if not data_dir.is_dir():
        print(f"Dataset not found: {data_dir}")
        print("  Run:  .venv/bin/python scripts/generate_demo_dataset.py")
        print("  Or:   .venv/bin/python scripts/download_dataset.py  (needs Kaggle token)")
        sys.exit(1)

    print(f"Dataset: {data_dir.resolve()}  protocol={args.protocol}")
    if args.protocol == "cross-session":
        result, id_result, persons, n_templates = _run_cross_session(args, data_dir)
    else:
        result, id_result, persons, n_templates = _run_single(args, data_dir)

    reports = args.reports_dir
    reports.mkdir(parents=True, exist_ok=True)
    roc_path = plot_roc(result, reports / "roc.png", title=f"ROC ({data_dir.name}, {args.protocol})")
    det_path = plot_det(result, reports / "det.png", title=f"DET ({data_dir.name}, {args.protocol})")

    calibration = {
        "dataset": str(data_dir.resolve()),
        "protocol": args.protocol,
        "pre_extracted": args.pre_extracted,
        "persons": persons,
        "templates": n_templates,
        "genuine_pairs": int(len(result.genuine_scores)),
        "impostor_pairs": int(len(result.impostor_scores)),
        "eer": round(result.eer, 4),
        "threshold": round(result.threshold, 4),
        "far_at_eer": round(result.far_at_eer, 4),
        "frr_at_eer": round(result.frr_at_eer, 4),
        "top1_accuracy": round(id_result.top1_accuracy, 4),
        "top1_probes": id_result.num_probes,
        "roc_plot": str(roc_path.resolve()),
        "det_plot": str(det_path.resolve()),
    }
    cal_path = reports / "calibration.json"
    cal_path.write_text(json.dumps(calibration, indent=2, ensure_ascii=False), encoding="utf-8")
    write_manifest(reports / "manifest.json", dataset=str(data_dir), count=n_templates, persons=persons)

    print("")
    print("=== Calibration Result ===")
    print(f"  Protocol   : {args.protocol}")
    print(f"  EER        : {result.eer:.2%}")
    print(f"  Threshold  : {result.threshold:.4f}  ← 已写入 calibration.json")
    print(f"  Top-1 Acc  : {id_result.top1_accuracy:.2%} ({id_result.num_correct}/{id_result.num_probes})")
    print(f"  ROC plot   : {roc_path}")
    print(f"  Report     : {cal_path}")


if __name__ == "__main__":
    main()
