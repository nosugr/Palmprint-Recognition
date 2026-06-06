"""Flask 应用工厂与本地 DEV 启动入口。"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask

import config
from hardware.bridge import create_bridge
from hardware.camera import create_camera
from server.routes import api
from server.stream import video_feed_response
from storage.repository import Repository

logger = logging.getLogger(__name__)


def create_app(
    *,
    use_serial: bool = False,
    camera_fallback: Path | str | None = None,
) -> Flask:
    app = Flask(__name__)

    repo = Repository()
    fallback = camera_fallback or (config.BASE_DIR / "data" / "demo" / "person_000")
    try:
        camera = create_camera(prefer_webcam=True, fallback_dir=fallback)
    except RuntimeError:
        camera = create_camera(prefer_webcam=False, fallback_dir=fallback)

    bridge = create_bridge(use_serial=use_serial)

    app.extensions["repo"] = repo
    app.extensions["camera"] = camera
    app.extensions["bridge"] = bridge

    app.register_blueprint(api, url_prefix="/api")

    @app.get("/video_feed")
    def video_feed():
        return video_feed_response(app.extensions["camera"])

    @app.teardown_appcontext
    def _shutdown(_exc=None):
        pass

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_app()
    logger.info("server http://%s:%s", config.SERVER_HOST, config.SERVER_PORT)
    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT, threaded=True)


if __name__ == "__main__":
    main()
