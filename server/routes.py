"""HTTP API 路由。"""

from __future__ import annotations

import time
from typing import Any

from flask import Blueprint, current_app, jsonify, request

import config
from algorithm.encode import encode
from algorithm.matcher import match_confidence, match_distance
from algorithm.preprocess import finalize_patch, to_gray
from algorithm.roi import extract_palm_roi_ex
from algorithm.template import mask_array
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


def _capture_encode():
    """抓多帧 → 各自做 ROI 提取 → 选纹路最清晰的一帧编码。

    单帧自动 ROI 约 30% 会失败；多帧选优把成功率拉高，并选出配准/清晰度最好的
    那帧，提升匹配一致性。全部失败时抛出带具体原因的 RuntimeError 供上层拒识。
    """
    repo, camera, _ = _services()
    del repo

    best = None  # (roi_quality, patch, patch_mask)
    reasons: list[str] = []
    got_frame = False
    for i in range(config.CAPTURE_FRAMES):
        frame = camera.read()
        if frame is None:
            continue
        got_frame = True
        res = extract_palm_roi_ex(to_gray(frame))
        if res.ok:
            if best is None or res.quality > best[0]:
                best = (res.quality, res.roi, res.mask, frame)
        else:
            reasons.append(res.reason)
        if i < config.CAPTURE_FRAMES - 1:
            time.sleep(config.CAPTURE_INTERVAL_MS / 1000.0)

    if not got_frame:
        raise RuntimeError("camera read failed")
    if best is None:
        # 取出现最多的失败原因作为提示
        reason = max(set(reasons), key=reasons.count) if reasons else "未检测到清晰掌纹，请重新放手"
        raise RuntimeError(reason)

    _, patch, patch_mask, frame = best
    roi, valid_mask = finalize_patch(patch, patch_mask)
    template = encode(roi, valid_mask)
    quality = float(mask_array(template).mean())
    return frame, template, quality


def _match_against_gallery(template) -> tuple[bool, dict | None, float, float]:
    repo, _, _ = _services()
    threshold = config.get_match_threshold()
    gallery = repo.load_gallery()
    if not gallery:
        return False, None, 1.0, threshold

    best_uid: int | None = None
    best_name: str | None = None
    best_dist = 1.0
    for uid, name, tmpl in gallery:
        d = match_distance(template, tmpl)
        if d < best_dist:
            best_dist = d
            best_uid = uid
            best_name = name

    matched = best_dist < threshold
    user = {"id": best_uid, "name": best_name} if matched and best_uid is not None else None
    return matched, user, best_dist, threshold


@api.post("/enroll")
def enroll():
    repo, _, _ = _services()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return _err("name is required")

    samples = int(body.get("samples") or config.ENROLL_SAMPLES)
    samples = max(1, min(samples, 20))

    user_id = repo.add_user(name)
    captured = 0
    quality_sum = 0.0

    for _ in range(samples):
        try:
            _, template, quality = _capture_encode()
        except RuntimeError as exc:
            if captured == 0:
                repo.delete_user(user_id)
                return _err(str(exc))
            break
        repo.add_template(user_id, template)
        captured += 1
        quality_sum += quality
        time.sleep(0.25)

    if captured == 0:
        repo.delete_user(user_id)
        return _err("failed to capture any sample")

    avg_quality = quality_sum / captured
    return _ok({"user_id": user_id, "captured": captured, "quality": round(avg_quality, 4)})


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
        _, template, _ = _capture_encode()
    except RuntimeError as exc:
        return _err(str(exc))

    matched, user, distance, threshold = _match_against_gallery(template)
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
        }
    )


@api.get("/preview_status")
def preview_status():
    """轻量探测当前画面里的手掌状态，供前端实时放手引导（不编码/不比对）。"""
    _, camera, _ = _services()
    frame = camera.read()
    if frame is None:
        return _ok({"ready": False, "status": "no_camera", "reason": "摄像头未就绪", "quality": 0.0})
    res = extract_palm_roi_ex(to_gray(frame))
    return _ok(
        {
            "ready": res.ok,
            "status": res.status,
            "reason": res.reason,
            "quality": round(res.quality, 2),
        }
    )


@api.get("/logs")
def logs():
    repo, _, _ = _services()
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 200))
    return _ok(repo.list_logs(limit))


@api.get("/health")
def health():
    repo, camera, bridge = _services()
    return _ok(
        {
            "db": True,
            "camera": camera.is_open(),
            "hardware": bridge.is_alive(),
        }
    )
