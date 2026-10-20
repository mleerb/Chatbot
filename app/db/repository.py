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
CREATE TABLE IF NOT EXISTS chat_conversations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New conversation',
    pinned BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS conversation_id BIGINT
    REFERENCES chat_conversations(id) ON DELETE CASCADE;
INSERT INTO chat_conversations (user_id, title)
    SELECT DISTINCT user_id, 'Conversation' FROM chat_messages WHERE conversation_id IS NULL;
UPDATE chat_messages AS m SET conversation_id = (
    SELECT c.id FROM chat_conversations AS c WHERE c.user_id = m.user_id ORDER BY c.id LIMIT 1
) WHERE m.conversation_id IS NULL;
ALTER TABLE chat_messages ALTER COLUMN conversation_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS chat_messages_conversation_id_id ON chat_messages (conversation_id, id);
CREATE INDEX IF NOT EXISTS chat_conversations_user_id ON chat_conversations (user_id);
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


def conversations(user_id):
    with connection() as conn:
        return conn.execute(
            "SELECT id, user_id, title, pinned FROM chat_conversations WHERE user_id = %s "
            "ORDER BY pinned DESC, id DESC", (user_id,)
        ).fetchall()


def create_conversation(user_id, title="New conversation"):
    with connection() as conn:
        return conn.execute(
            "INSERT INTO chat_conversations (user_id, title) VALUES (%s, %s) "
            "RETURNING id, user_id, title, pinned", (user_id, title)
        ).fetchone()


def get_conversation(user_id, conversation_id):
    with connection() as conn:
        return conn.execute(
            "SELECT id, user_id, title, pinned FROM chat_conversations WHERE user_id = %s AND id = %s",
            (user_id, conversation_id),
        ).fetchone()


def update_conversation(user_id, conversation_id, title=None, pinned=None):
    with connection() as conn:
        return conn.execute(
            "UPDATE chat_conversations SET title = COALESCE(%s, title), pinned = COALESCE(%s, pinned) "
            "WHERE user_id = %s AND id = %s RETURNING id, user_id, title, pinned",
            (title, pinned, user_id, conversation_id),
        ).fetchone()


def delete_conversation(user_id, conversation_id):
    with connection() as conn:
        return conn.execute(
            "DELETE FROM chat_conversations WHERE user_id = %s AND id = %s RETURNING id",
            (user_id, conversation_id),
        ).fetchone()


def messages(user_id, limit=None, conversation_id=None):
    with connection() as conn:
        if limit is None:
            rows = conn.execute(
                "SELECT role, content, sources FROM chat_messages WHERE user_id = %s "
                "AND (%s::bigint IS NULL OR conversation_id = %s) ORDER BY id",
                (user_id, conversation_id, conversation_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT role, content, sources FROM chat_messages WHERE user_id = %s "
                "AND (%s::bigint IS NULL OR conversation_id = %s) ORDER BY id DESC LIMIT %s",
                (user_id, conversation_id, conversation_id, limit),
            ).fetchall()[::-1]
        return rows


def save_turn(user_id, question, answer, sources, conversation_id):
    from psycopg.types.json import Jsonb

    with connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, conversation_id, role, content) VALUES (%s, %s, 'user', %s)",
            (user_id, conversation_id, question),
        )
        conn.execute(
            "INSERT INTO chat_messages (user_id, conversation_id, role, content, sources) "
            "VALUES (%s, %s, 'assistant', %s, %s)",
            (user_id, conversation_id, answer, Jsonb(sources)),
        )
