from __future__ import annotations

import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.getenv("LAB05_DB_PATH", DATA_DIR / "lab05.sqlite"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    users_count = int(os.getenv("LAB05_USERS", "1000"))
    posts_count = int(os.getenv("LAB05_POSTS", "10000"))
    comments_count = int(os.getenv("LAB05_COMMENTS", "50000"))

    conn = get_connection()
    try:
        _create_schema(conn)
        if _has_expected_data(conn, users_count, posts_count, comments_count):
            return
        _reset_data(conn)
        _seed_data(conn, users_count, posts_count, comments_count)
    finally:
        conn.close()


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            city TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            author_id INTEGER NOT NULL,
            FOREIGN KEY (author_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            post_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (author_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts(author_id);
        CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
        """
    )


def _has_expected_data(conn: sqlite3.Connection, users_count: int, posts_count: int, comments_count: int) -> bool:
    counts = {
        "users": users_count,
        "posts": posts_count,
        "comments": comments_count,
    }
    for table, expected in counts.items():
        actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if actual != expected:
            return False
    return True


def _reset_data(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM comments;
        DELETE FROM posts;
        DELETE FROM users;
        """
    )
    conn.commit()


def _seed_data(conn: sqlite3.Connection, users_count: int, posts_count: int, comments_count: int) -> None:
    cities = ["Curitiba", "Porto Alegre", "Sao Paulo", "Rio de Janeiro", "Belo Horizonte"]
    users = (
        (
            user_id,
            f"User {user_id:04d}",
            f"user{user_id:04d}@example.com",
            f"+55 41 9{user_id % 10000:04d}-{(user_id * 7) % 10000:04d}",
            cities[user_id % len(cities)],
        )
        for user_id in range(1, users_count + 1)
    )
    conn.executemany("INSERT INTO users (id, name, email, phone, city) VALUES (?, ?, ?, ?, ?)", users)

    posts = (
        (
            post_id,
            f"Post {post_id:05d}",
            f"Body of post {post_id:05d}. This text is deterministic for the controlled experiment.",
            ((post_id - 1) % users_count) + 1,
        )
        for post_id in range(1, posts_count + 1)
    )
    conn.executemany("INSERT INTO posts (id, title, body, author_id) VALUES (?, ?, ?, ?)", posts)

    comments = (
        (
            comment_id,
            f"Comment {comment_id:05d} for post {((comment_id - 1) % posts_count) + 1:05d}.",
            ((comment_id - 1) % posts_count) + 1,
            ((comment_id * 13 - 1) % users_count) + 1,
        )
        for comment_id in range(1, comments_count + 1)
    )
    conn.executemany("INSERT INTO comments (id, text, post_id, author_id) VALUES (?, ?, ?, ?)", comments)
    conn.commit()
