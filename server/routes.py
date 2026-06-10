"""HTTP API 路由。"""

from __future__ import annotations

import time
from typing import Any

from flask import Blueprint, current_app, jsonify, request

import config
from algorithm.encode import encode
from algorithm.matcher import match_confidence, match_distance
from algorithm.preprocess import finalize_patch, to_gray
from algorithm.roi import _roi_quality, extract_palm_roi_ex, get_detect_stats, reset_detect_stats
from hardware.camera import SwitchableCamera
from hardware.probe import probe_cameras
from storage.repository import Repository

api = Blueprint("api", __name__)


def _ok(data: Any = None, status: int = 200):
    return jsonify({"ok": True, "data": data, "error": None}), status


def _err(message: str, status: int = 400):
    return jsonify({"ok": False, "data": None, "error": message}), status


def _services():
    return (
        current_app.extensions["repo"],
        current_app.extensions["camera"],
        current_app.extensions["bridge"],
    )


def _capture_encode_multi() -> list[tuple[Any, Any, float, str]]:
    """抓多帧 → 每个 ROI 提取成功的帧各自编码。

    返回 [(frame, template, quality, hand_side), ...]（至少 1 个）。
    单帧自动 ROI 有一定失败率；多帧把成功率拉高，验证时还可对多个模板分别
    比对取最小距离（多帧融合），抵消单帧关键点抖动带来的配准误差。
    全部失败时抛出带具体原因的 RuntimeError 供上层拒识。
    """
    _, camera, _ = _services()

    candidates = []  # (patch, patch_mask, frame, hand_side)
    reasons: list[str] = []
    got_frame = False
    for i in range(config.CAPTURE_FRAMES):
        frame = camera.read()
        if frame is None:
            continue
        got_frame = True
        res = extract_palm_roi_ex(to_gray(frame), bgr=frame)
        if res.ok:
            candidates.append((res.roi, res.mask, frame, res.hand_side))
        else:
            reasons.append(res.reason)
        if i < config.CAPTURE_FRAMES - 1:
            time.sleep(config.CAPTURE_INTERVAL_MS / 1000.0)

    if not got_frame:
        raise RuntimeError("camera read failed")
    if not candidates:
        reason = max(set(reasons), key=reasons.count) if reasons else "未检测到清晰掌纹，请重新放手"
        raise RuntimeError(reason)

    out: list[tuple[Any, Any, float, str]] = []
    for patch, patch_mask, frame, hand_side in candidates:
        roi, valid_mask = finalize_patch(patch, patch_mask)
        template = encode(roi, valid_mask)
        coverage = float(valid_mask.mean())
        clarity, contrast = _roi_quality(roi)
        quality = 0.5 * coverage + 0.3 * clarity + 0.2 * contrast
        out.append((frame, template, quality, hand_side))
    return out


def _capture_encode():
    """单模板版本：多帧候选中取质量最高的一个（注册场景用）。"""
    return max(_capture_encode_multi(), key=lambda c: c[2])


def _match_against_gallery(probes: list[tuple[Any, str]]) -> tuple[bool, dict | None, float, float, str]:
    """probes: [(template, hand_side), ...]，逐个与库比对，取全局最小距离。

    手别过滤：探针手别已知且库中存在同手别模板时只比同手别，减少误匹配；
    库中无同手别模板时回退全库，避免手别偶发误判导致擦肩拒识。
    """
    repo, _, _ = _services()
    threshold = config.get_match_threshold()
    gallery = repo.load_gallery()
    if not gallery or not probes:
        return False, None, 1.0, threshold, ""

    best_uid: int | None = None
    best_name: str | None = None
    best_dist = 1.0
    best_hand = ""
    for probe, probe_hand in probes:
        candidates = [g for g in gallery if g[3] == probe_hand] if probe_hand else []
        if not candidates:
            candidates = gallery
        for uid, name, tmpl, hand_side in candidates:
            d = match_distance(probe, tmpl)
            if d < best_dist:
                best_dist = d
                best_uid = uid
                best_name = name
                best_hand = hand_side

    matched = best_dist < threshold
    user = {"id": best_uid, "name": best_name} if matched and best_uid is not None else None
    return matched, user, best_dist, threshold, best_hand


@api.post("/enroll")
def enroll():
    repo, _, _ = _services()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return _err("name is required")

    samples = int(body.get("samples") or config.ENROLL_SAMPLES)
    samples = max(1, min(samples, 20))

    # 按名字查找已有用户，不存在则新建
    existing = repo.get_user_by_name(name)
    if existing:
        user_id = existing["id"]
    else:
        user_id = repo.add_user(name)

    captured = 0
    quality_sum = 0.0
    detected_hand = ""

    for _ in range(samples):
        try:
            _, template, quality, hand_side = _capture_encode()
        except RuntimeError as exc:
            if captured == 0 and not existing:
                repo.delete_user(user_id)
                return _err(str(exc))
            break

        if not detected_hand:
            detected_hand = hand_side

        # 同一轮注册只接受同一只手的采样，检测到不同手则跳过该帧
        if hand_side != detected_hand:
            continue

        repo.add_template(user_id, template, hand_side, quality)
        # 新旧模板合并后按质量只保留前 N 张：既避免重注册时收缩成单张
        # （模板越多同掌最小距离越小），也防止反复注册导致模板无限增长
        tmpls = [
            t for t in repo.get_templates_by_user_hand(user_id, hand_side)
            if t["version"] == config.TEMPLATE_VERSION
        ]
        if len(tmpls) > config.MAX_TEMPLATES_PER_HAND:
            tmpls.sort(key=lambda t: t["quality"], reverse=True)
            for old in tmpls[config.MAX_TEMPLATES_PER_HAND :]:
                repo.delete_template(old["id"])
        captured += 1
        quality_sum += quality
        time.sleep(0.25)

    if captured == 0:
        if not existing:
            repo.delete_user(user_id)
        return _err("failed to capture any sample")

    avg_quality = quality_sum / captured
    return _ok({
        "user_id": user_id,
        "captured": captured,
        "quality": round(avg_quality, 4),
        "hand_side": detected_hand,
    })


@api.get("/users")
def users():
    repo, _, _ = _services()
    return _ok(repo.list_users())


@api.delete("/users/<int:user_id>")
def delete_user(user_id: int):
    repo, _, _ = _services()
    deleted = repo.delete_user(user_id)
    if deleted == 0:
        return _err("user not found", 404)
    return _ok({"deleted": deleted})


@api.post("/verify")
def verify():
    repo, _, bridge = _services()
    try:
        candidates = _capture_encode_multi()
    except RuntimeError as exc:
        return _err(str(exc))

    # 质量最高的前 N 帧参与比对（多帧融合取最小距离），N 限制匹配延迟
    candidates.sort(key=lambda c: c[2], reverse=True)
    probes = [(tmpl, hand) for _, tmpl, _, hand in candidates[: config.VERIFY_PROBE_FRAMES]]

    matched, user, distance, threshold, hand_side = _match_against_gallery(probes)
    user_id = user["id"] if user else None
    repo.add_log(
        user_id=user_id,
        matched=matched,
        distance=distance,
        threshold=threshold,
    )

    if matched:
        bridge.unlock(config.UNLOCK_MS)
        bridge.indicate(True)
    else:
        bridge.indicate(False)

    return _ok(
        {
            "matched": matched,
            "user": user,
            "distance": round(distance, 4),
            "threshold": round(threshold, 4),
            "confidence": round(match_confidence(distance, threshold), 4),
            "hand_side": hand_side,
        }
    )


@api.get("/preview_status")
def preview_status():
    """轻量探测当前画面里的手掌状态，供前端实时放手引导（不编码/不比对）。"""
    _, camera, _ = _services()
    frame = camera.read()
    if frame is None:
        return _ok({"ready": False, "status": "no_camera", "reason": "摄像头未就绪", "quality": 0.0, "solidity": None})
    res = extract_palm_roi_ex(to_gray(frame), bgr=frame)
    return _ok(
        {
            "ready": res.ok,
            "status": res.status,
            "reason": res.reason,
            "quality": res.quality,
            "solidity": None,
        }
    )


@api.get("/detect_stats")
def detect_stats():
    """ROI 检测各阶段命中/拒识计数直方图（诊断用）。?reset=1 时返回当前值后清零。"""
    stats = get_detect_stats()
    if request.args.get("reset") in ("1", "true", "yes"):
        reset_detect_stats()
    return _ok(stats)


@api.get("/logs")
def logs():
    repo, _, _ = _services()
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 200))
    return _ok(repo.list_logs(limit))


@api.get("/cameras")
def cameras():
    """探测可用摄像头列表 + 当前正在使用的索引。

    探测会独占式打开设备，故跳过当前正在使用的索引（否则会把实时画面抢断），
    该索引单独用当前摄像头的状态合成一条。
    """
    _, camera, _ = _services()
    current_index = getattr(camera, "current_index", None)
    indices = [i for i in range(config.CAMERA_PROBE_COUNT) if i != current_index]
    cams = probe_cameras(indices)
    if current_index is not None:
        # 正在使用的摄像头无法重复打开探测，直接读一帧拿真实分辨率。
        frame = camera.read()
        h, w = (frame.shape[:2] if frame is not None else (0, 0))
        cams.append(
            {
                "index": current_index,
                "available": camera.is_open(),
                "width": int(w),
                "height": int(h),
            }
        )
    cams.sort(key=lambda c: c["index"])
    return _ok({"cameras": cams, "current_index": current_index})


@api.post("/camera/select")
def camera_select():
    """切换到指定摄像头索引，成功后持久化为下次启动的默认。"""
    _, camera, _ = _services()
    body = request.get_json(silent=True) or {}
    if "index" not in body:
        return _err("index is required")
    try:
        index = int(body["index"])
    except (TypeError, ValueError):
        return _err("index must be an integer")

    if not isinstance(camera, SwitchableCamera):
        return _err("camera does not support switching")
    if not camera.switch(index):
        return _err(f"failed to open camera {index}")

    config.save_default_camera_index(index)
    return _ok({"index": index})


@api.get("/health")
def health():
    repo, camera, bridge = _services()
    return _ok(
        {
            "db": True,
            "camera": camera.is_open(),
            "hardware": bridge.status(),
        }
    )
