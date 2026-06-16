from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from api.internal.database import get_connection, initialize_database
from api.internal.services import LabService


HOST = os.getenv("LAB05_HOST", "127.0.0.1")
PORT = int(os.getenv("LAB05_PORT", "8000"))


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class LabRequestHandler(BaseHTTPRequestHandler):
    server_version = "Lab05API/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.strip("/")
        query = parse_qs(parsed.query)
        service = LabService(get_connection())

        try:
            if path == "health":
                self._send_json({"status": "ok"})
                return

            if path == "users":
                page = _parse_int(query.get("page", ["1"])[0], 1)
                limit = _parse_int(query.get("limit", ["50"])[0], 50)
                self._send_json({"data": service.list_users(page=page, limit=limit, fields=None)})
                return

            user_match = re.fullmatch(r"users/(\d+)", path)
            if user_match:
                user_id = int(user_match.group(1))
                user = service.get_user(user_id, fields=None)
                if user is None:
                    self._send_json({"error": "user not found"}, status=404)
                else:
                    self._send_json({"data": user})
                return

            posts_match = re.fullmatch(r"users/(\d+)/posts", path)
            if posts_match:
                user_id = int(posts_match.group(1))
                self._send_json({"data": service.get_posts_by_user(user_id, fields=None)})
                return

            comments_match = re.fullmatch(r"posts/(\d+)/comments", path)
            if comments_match:
                post_id = int(comments_match.group(1))
                self._send_json({"data": service.get_comments_by_post(post_id, fields=None)})
                return

            self._send_json({"error": "not found"}, status=404)
        finally:
            service.close()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/graphql":
            self._send_json({"error": "not found"}, status=404)
            return

        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            self._send_json({"errors": [{"message": "invalid JSON body"}]}, status=400)
            return

        query = str(payload.get("query", ""))
        service = LabService(get_connection())
        try:
            response = execute_graphql_query(service, query)
            status = 200 if "errors" not in response else 400
            self._send_json(response, status=status)
        finally:
            service.close()

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("LAB05_ACCESS_LOG", "0") == "1":
            super().log_message(fmt, *args)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def execute_graphql_query(service: LabService, query: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", query).strip()

    users_match = re.search(r"users\s*\(\s*page\s*:\s*(\d+)\s*,\s*limit\s*:\s*(\d+)\s*\)", compact)
    if users_match:
        page = int(users_match.group(1))
        limit = int(users_match.group(2))
        return {"data": {"users": service.list_users(page=page, limit=limit, fields=["id", "name", "city"])}}

    user_match = re.search(r"user\s*\(\s*id\s*:\s*(\d+)\s*\)", compact)
    if not user_match:
        return {"errors": [{"message": "unsupported query"}]}

    user_id = int(user_match.group(1))

    if "posts" not in compact:
        user = service.get_user(user_id, fields=["id", "name", "email"])
        return {"data": {"user": user}}

    if "body" in compact or "phone" in compact or "authorId" in compact:
        user = service.get_user_with_posts_and_comments(
            user_id,
            user_fields=["id", "name", "email", "phone", "city"],
            post_fields=["id", "title", "body", "authorId"],
            comment_fields=["id", "text", "postId", "authorId"],
        )
        return {"data": {"user": user}}

    if "comments" in compact:
        user = service.get_user_with_posts_and_comments(
            user_id,
            user_fields=["id", "name"],
            post_fields=["id", "title"],
            comment_fields=["id", "text"],
        )
        return {"data": {"user": user}}

    user = service.get_user_with_posts(user_id, user_fields=["id"], post_fields=["title"])
    return {"data": {"user": user}}


def main() -> None:
    initialize_database()
    httpd = ThreadingHTTPServer((HOST, PORT), LabRequestHandler)
    print(f"Lab05 API running at http://{HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
