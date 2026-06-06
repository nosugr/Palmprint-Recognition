"""users / templates / logs 数据访问。"""

from __future__ import annotations

import sqlite3
from typing import Any

import config
from algorithm.template import PalmTemplate
from storage.db import connect, init_db


class Repository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn if conn is not None else connect()
        init_db(self._conn)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def add_user(self, name: str) -> int:
        cur = self._conn.execute("INSERT INTO users (name) VALUES (?)", (name.strip(),))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_users(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT u.id, u.name, u.created_at,
                   COUNT(t.id) AS template_count
            FROM users u
            LEFT JOIN templates t ON t.user_id = u.id
            GROUP BY u.id
            ORDER BY u.id
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_user(self, user_id: int) -> int:
        cur = self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self._conn.commit()
        return cur.rowcount

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT id, name, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def add_template(self, user_id: int, template: PalmTemplate) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO templates
                (user_id, code, mask, height, width, bits_per_pixel, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                template.code,
                template.mask,
                template.height,
                template.width,
                template.bits_per_pixel,
                template.version,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def load_gallery(self) -> list[tuple[int, str, PalmTemplate]]:
        """仅返回与当前编码版本兼容的模板；旧版本模板被忽略（需重新注册）。"""
        rows = self._conn.execute(
            """
            SELECT t.user_id, u.name, t.code, t.mask, t.height, t.width,
                   t.bits_per_pixel, t.version
            FROM templates t
            JOIN users u ON u.id = t.user_id
            WHERE t.version = ?
            """,
            (config.TEMPLATE_VERSION,),
        ).fetchall()
        gallery: list[tuple[int, str, PalmTemplate]] = []
        for r in rows:
            tmpl = PalmTemplate(
                code=bytes(r["code"]),
                mask=bytes(r["mask"]),
                height=r["height"],
                width=r["width"],
                bits_per_pixel=r["bits_per_pixel"],
                version=r["version"],
            )
            gallery.append((r["user_id"], r["name"], tmpl))
        return gallery

    def add_log(
        self,
        *,
        user_id: int | None,
        matched: bool,
        distance: float,
        threshold: float,
        image_path: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO logs (user_id, matched, distance, threshold, image_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, int(matched), distance, threshold, image_path),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT l.id, l.user_id, u.name AS user_name, l.matched,
                   l.distance, l.threshold, l.created_at
            FROM logs l
            LEFT JOIN users u ON u.id = l.user_id
            ORDER BY l.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
