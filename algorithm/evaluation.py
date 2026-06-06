"""S1.4 性能评估：FAR/FRR、EER 与 ROC 曲线。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config
from algorithm.matcher import match_distance, match_distance_arrays
from algorithm.template import PalmTemplate, code_array, mask_array


@dataclass
class EERResult:
    eer: float
    threshold: float
    far_at_eer: float
    frr_at_eer: float
    genuine_scores: np.ndarray
    impostor_scores: np.ndarray


def pairwise_scores(
    templates: list[PalmTemplate],
    labels: list[int],
    *,
    max_impostor_pairs: int | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """返回 (genuine_distances, impostor_distances)。impostor 过多时可抽样。"""
    genuine: list[float] = []
    impostor: list[float] = []
    n = len(templates)
    for i in range(n):
        for j in range(i + 1, n):
            d = match_distance(templates[i], templates[j])
            if labels[i] == labels[j]:
                genuine.append(d)
            else:
                impostor.append(d)

    gen = np.array(genuine, dtype=np.float64)
    imp = np.array(impostor, dtype=np.float64)

    if max_impostor_pairs is not None and len(imp) > max_impostor_pairs:
        r = rng if rng is not None else np.random.default_rng(42)
        idx = r.choice(len(imp), size=max_impostor_pairs, replace=False)
        imp = imp[idx]
    return gen, imp


def _arrayize(items: list[tuple[int, PalmTemplate]]) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """预解包模板为 (pid, code, mask) 数组，避免批量匹配时反复 unpackbits。"""
    return [(pid, code_array(t), mask_array(t)) for pid, t in items]


def cross_session_scores(
    enroll: list[tuple[int, PalmTemplate]],
    probe: list[tuple[int, PalmTemplate]],
    *,
    max_impostor_pairs: int | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """跨 session 打分：enroll（如 session1）作底库，probe（session2）作查询。

    genuine = 同掌的 (enroll, probe) 对；impostor = 异掌的 (enroll, probe) 对。
    impostor 数量庞大时按 max_impostor_pairs 随机抽样。
    """
    n_dirs = config.GABOR_ORIENTATIONS
    by_palm_enroll: dict[int, list[tuple[np.ndarray, np.ndarray]]] = {}
    for pid, c, m in _arrayize(enroll):
        by_palm_enroll.setdefault(pid, []).append((c, m))
    probe_arr = _arrayize(probe)

    genuine: list[float] = []
    impostor: list[float] = []
    r = rng if rng is not None else np.random.default_rng(42)

    enroll_pids = list(by_palm_enroll.keys())
    for pid, pc, pm in probe_arr:
        for ec, em in by_palm_enroll.get(pid, []):
            genuine.append(match_distance_arrays(ec, em, pc, pm, n_dirs=n_dirs))

    # impostor：每个 probe 对若干个异掌 enroll 模板抽样
    imp_per_probe = 6
    for pid, pc, pm in probe_arr:
        others = [q for q in enroll_pids if q != pid]
        if not others:
            continue
        chosen = r.choice(len(others), size=min(imp_per_probe, len(others)), replace=False)
        for ci in chosen:
            cand = by_palm_enroll[others[int(ci)]]
            ec, em = cand[int(r.integers(len(cand)))]
            impostor.append(match_distance_arrays(ec, em, pc, pm, n_dirs=n_dirs))

    gen = np.array(genuine, dtype=np.float64)
    imp = np.array(impostor, dtype=np.float64)
    if max_impostor_pairs is not None and len(imp) > max_impostor_pairs:
        idx = r.choice(len(imp), size=max_impostor_pairs, replace=False)
        imp = imp[idx]
    return gen, imp


def evaluate_identification_cross_session(
    enroll: list[tuple[int, PalmTemplate]],
    probe: list[tuple[int, PalmTemplate]],
    *,
    threshold: float,
    gallery_per_palm: int = 1,
    max_shift: int = 3,
) -> "IdentificationResult":
    """开集识别：每个 probe 在底库里找最近邻，算 Top-1（带阈值）。

    底库每掌仅取 ``gallery_per_palm`` 个模板（默认 1，模拟单次注册场景）；
    ``max_shift=3`` 做小范围平移补偿（shift=0 会因配准残差显著降低 Top-1）。
    """
    n_dirs = config.GABOR_ORIENTATIONS
    gallery: list[tuple[int, np.ndarray, np.ndarray]] = []
    seen: dict[int, int] = {}
    for pid, c, m in _arrayize(enroll):
        if seen.get(pid, 0) < gallery_per_palm:
            gallery.append((pid, c, m))
            seen[pid] = seen.get(pid, 0) + 1
    probe_arr = _arrayize(probe)

    correct = 0
    for true_pid, pc, pm in probe_arr:
        best_pid: int | None = None
        best_dist = 1.0
        for gid, gc, gm in gallery:
            d = match_distance_arrays(pc, pm, gc, gm, max_shift=max_shift, n_dirs=n_dirs)
            if d < best_dist:
                best_dist = d
                best_pid = gid
        if best_dist < threshold and best_pid == true_pid:
            correct += 1
    n = len(probe_arr)
    return IdentificationResult(
        top1_accuracy=correct / n if n else 0.0,
        num_probes=n,
        num_correct=correct,
        threshold=threshold,
    )


def compute_far_frr(
    genuine: np.ndarray,
    impostor: np.ndarray,
    thresholds: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    far = np.array([(impostor < t).mean() if len(impostor) else 0.0 for t in thresholds])
    frr = np.array([(genuine >= t).mean() if len(genuine) else 0.0 for t in thresholds])
    return far, frr


def compute_eer(genuine: np.ndarray, impostor: np.ndarray) -> EERResult:
    if len(genuine) == 0 or len(impostor) == 0:
        raise ValueError("need both genuine and impostor pairs")

    all_scores = np.concatenate([genuine, impostor])
    thresholds = np.linspace(all_scores.min(), all_scores.max(), 200)
    far, frr = compute_far_frr(genuine, impostor, thresholds)
    idx = int(np.argmin(np.abs(far - frr)))
    return EERResult(
        eer=float((far[idx] + frr[idx]) / 2),
        threshold=float(thresholds[idx]),
        far_at_eer=float(far[idx]),
        frr_at_eer=float(frr[idx]),
        genuine_scores=genuine,
        impostor_scores=impostor,
    )


def plot_roc(
    result: EERResult,
    out_path: str | Path,
    *,
    title: str = "Palmprint ROC",
) -> Path:
    thresholds = np.linspace(
        min(result.genuine_scores.min(), result.impostor_scores.min()),
        max(result.genuine_scores.max(), result.impostor_scores.max()),
        200,
    )
    far, frr = compute_far_frr(result.genuine_scores, result.impostor_scores, thresholds)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(far, 1 - frr, label="ROC")
    ax.plot([0, 1], [0, 1], "--", color="gray", linewidth=0.8)
    ax.scatter([result.far_at_eer], [1 - result.frr_at_eer], color="red", zorder=5, label=f"EER={result.eer:.3f}")
    ax.set_xlabel("FAR")
    ax.set_ylabel("1 - FRR (TPR)")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_det(
    result: EERResult,
    out_path: str | Path,
    *,
    title: str = "Palmprint DET",
) -> Path:
    thresholds = np.linspace(
        min(result.genuine_scores.min(), result.impostor_scores.min()),
        max(result.genuine_scores.max(), result.impostor_scores.max()),
        200,
    )
    far, frr = compute_far_frr(result.genuine_scores, result.impostor_scores, thresholds)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(far, frr, label="DET")
    ax.scatter([result.far_at_eer], [result.frr_at_eer], color="red", zorder=5, label=f"EER={result.eer:.3f}")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("FAR")
    ax.set_ylabel("FRR")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


@dataclass
class IdentificationResult:
    top1_accuracy: float
    num_probes: int
    num_correct: int
    threshold: float


def evaluate_identification(
    pairs: list[tuple[int, PalmTemplate]],
    *,
    enroll_per_person: int = 2,
    threshold: float,
) -> IdentificationResult:
    """每人前 enroll_per_person 张作模板，其余作 probe，算 Top-1。"""
    by_person: dict[int, list[PalmTemplate]] = {}
    for pid, tmpl in pairs:
        by_person.setdefault(pid, []).append(tmpl)

    gallery: list[tuple[int, PalmTemplate]] = []
    probes: list[tuple[int, PalmTemplate]] = []
    for pid, tmpls in by_person.items():
        if len(tmpls) <= enroll_per_person:
            gallery.extend((pid, t) for t in tmpls)
            continue
        for t in tmpls[:enroll_per_person]:
            gallery.append((pid, t))
        for t in tmpls[enroll_per_person:]:
            probes.append((pid, t))

    if not probes:
        raise ValueError("no probe samples; need more than enroll_per_person images per person")

    correct = 0
    for true_pid, probe in probes:
        best_pid: int | None = None
        best_dist = 1.0
        for gid, gt in gallery:
            d = match_distance(probe, gt)
            if d < best_dist:
                best_dist = d
                best_pid = gid
        if best_dist < threshold and best_pid == true_pid:
            correct += 1

    n = len(probes)
    return IdentificationResult(
        top1_accuracy=correct / n,
        num_probes=n,
        num_correct=correct,
        threshold=threshold,
    )
