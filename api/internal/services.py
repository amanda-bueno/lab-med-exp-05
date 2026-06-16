from __future__ import annotations

import sqlite3
from typing import Iterable


USER_COLUMNS = {
    "id": "id",
    "name": "name",
    "email": "email",
    "phone": "phone",
    "city": "city",
}
POST_COLUMNS = {
    "id": "id",
    "title": "title",
    "body": "body",
    "authorId": "author_id",
}
COMMENT_COLUMNS = {
    "id": "id",
    "text": "text",
    "postId": "post_id",
    "authorId": "author_id",
}


def _columns(allowed: dict[str, str], fields: Iterable[str] | None) -> str:
    selected = list(fields) if fields else list(allowed)
    return ", ".join(f"{allowed[field]} AS {field}" for field in selected)


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


class LabService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def close(self) -> None:
        self.conn.close()

    def get_user(self, user_id: int, fields: list[str] | None) -> dict | None:
        cols = _columns(USER_COLUMNS, fields)
        row = self.conn.execute(f"SELECT {cols} FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_dict(row)

    def list_users(self, page: int, limit: int, fields: list[str] | None) -> list[dict]:
        cols = _columns(USER_COLUMNS, fields)
        offset = max(page - 1, 0) * limit
        rows = self.conn.execute(
            f"SELECT {cols} FROM users ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_posts_by_user(self, user_id: int, fields: list[str] | None) -> list[dict]:
        cols = _columns(POST_COLUMNS, fields)
        rows = self.conn.execute(
            f"SELECT {cols} FROM posts WHERE author_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_comments_by_post(self, post_id: int, fields: list[str] | None) -> list[dict]:
        cols = _columns(COMMENT_COLUMNS, fields)
        rows = self.conn.execute(
            f"SELECT {cols} FROM comments WHERE post_id = ? ORDER BY id",
            (post_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_user_with_posts(self, user_id: int, user_fields: list[str], post_fields: list[str]) -> dict | None:
        user = self.get_user(user_id, user_fields)
        if user is None:
            return None
        user["posts"] = self.get_posts_by_user(user_id, post_fields)
        return user

    def get_user_with_posts_and_comments(
        self,
        user_id: int,
        user_fields: list[str],
        post_fields: list[str],
        comment_fields: list[str],
    ) -> dict | None:
        user = self.get_user_with_posts(user_id, user_fields, post_fields)
        if user is None:
            return None
        for post in user["posts"]:
            post["comments"] = self.get_comments_by_post(post["id"], comment_fields)
        return user
