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
        Base.metadata.create_all(connection)
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(connection, checkfirst=True)
