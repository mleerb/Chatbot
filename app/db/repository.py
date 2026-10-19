from app.db.connection import connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_user_id_id ON chat_messages (user_id, id);
"""


def initialize():
    with connection() as conn:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)


def users():
    with connection() as conn:
        return conn.execute("SELECT id, name FROM chat_users ORDER BY name, id").fetchall()


def create_user(name):
    with connection() as conn:
        return conn.execute("INSERT INTO chat_users (name) VALUES (%s) RETURNING id, name", (name,)).fetchone()


def get_user(user_id):
    with connection() as conn:
        return conn.execute("SELECT id, name FROM chat_users WHERE id = %s", (user_id,)).fetchone()


def messages(user_id, limit=None):
    with connection() as conn:
        if limit is None:
            rows = conn.execute(
                "SELECT role, content, sources FROM chat_messages WHERE user_id = %s ORDER BY id", (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT role, content, sources FROM chat_messages WHERE user_id = %s ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()[::-1]
        return rows


def save_turn(user_id, question, answer, sources):
    from psycopg.types.json import Jsonb

    with connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (%s, 'user', %s)",
            (user_id, question),
        )
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, sources) VALUES (%s, 'assistant', %s, %s)",
            (user_id, answer, Jsonb(sources)),
        )
