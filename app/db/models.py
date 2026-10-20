from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, JSON, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


identifier = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "chat_users"

    id: Mapped[int] = mapped_column(identifier, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "chat_accounts"

    id: Mapped[int] = mapped_column(identifier, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("chat_users.id", ondelete="CASCADE"), unique=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (Index("chat_conversations_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(identifier, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("chat_users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text, server_default="New conversation")
    pinned: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="chat_messages_role_check"),
        Index("chat_messages_user_id_id", "user_id", "id"),
        Index("chat_messages_conversation_id_id", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(identifier, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("chat_users.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("chat_conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[dict[str, str]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
