from sqlalchemy import inspect, text

from app.db.models import Base, Conversation, User


def initialize_schema(engine):
    with engine.begin() as connection:
        User.__table__.create(connection, checkfirst=True)
        Conversation.__table__.create(connection, checkfirst=True)
        inspector = inspect(connection)
        if connection.dialect.name == "postgresql" and inspector.has_table("chat_messages"):
            columns = {column["name"]: column for column in inspector.get_columns("chat_messages")}
            if "conversation_id" not in columns:
                connection.execute(text(
                    "ALTER TABLE chat_messages ADD COLUMN conversation_id BIGINT "
                    "REFERENCES chat_conversations(id) ON DELETE CASCADE"
                ))
            if "conversation_id" not in columns or columns["conversation_id"]["nullable"]:
                connection.execute(text(
                    "INSERT INTO chat_conversations (user_id, title) "
                    "SELECT DISTINCT user_id, 'Conversation' FROM chat_messages WHERE conversation_id IS NULL"
                ))
                connection.execute(text(
                    "UPDATE chat_messages AS m SET conversation_id = ("
                    "SELECT c.id FROM chat_conversations AS c WHERE c.user_id = m.user_id ORDER BY c.id LIMIT 1"
                    ") WHERE m.conversation_id IS NULL"
                ))
                connection.execute(text("ALTER TABLE chat_messages ALTER COLUMN conversation_id SET NOT NULL"))
        if inspector.has_table("chat_messages") and "attachments" not in {
            column["name"] for column in inspector.get_columns("chat_messages")
        }:
            kind = "JSONB" if connection.dialect.name == "postgresql" else "JSON"
            connection.execute(text(f"ALTER TABLE chat_messages ADD COLUMN attachments {kind} NOT NULL DEFAULT '[]'"))
        if inspector.has_table("chat_messages"):
            existing = {column["name"] for column in inspector.get_columns("chat_messages")}
            if "stopped" not in existing:
                connection.execute(text("ALTER TABLE chat_messages ADD COLUMN stopped BOOLEAN NOT NULL DEFAULT false"))
            if "rating" not in existing:
                check = " CHECK (rating IN ('up', 'down'))" if connection.dialect.name == "postgresql" else ""
                connection.execute(text(f"ALTER TABLE chat_messages ADD COLUMN rating TEXT{check}"))
            if "trace_id" not in existing:
                connection.execute(text("ALTER TABLE chat_messages ADD COLUMN trace_id TEXT"))
        if inspector.has_table("chat_usage"):
            existing = {column["name"] for column in inspector.get_columns("chat_usage")}
            for name in ("uploads", "images"):
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE chat_usage ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"))
        if inspector.has_table("chat_files") and "embeddings" not in {
            column["name"] for column in inspector.get_columns("chat_files")
        }:
            kind = "BYTEA" if connection.dialect.name == "postgresql" else "BLOB"
            connection.execute(text(f"ALTER TABLE chat_files ADD COLUMN embeddings {kind}"))
        Base.metadata.create_all(connection)
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(connection, checkfirst=True)
