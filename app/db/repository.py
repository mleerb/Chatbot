from sqlalchemy import delete, select, update

from app.db.connection import get_engine, session
from app.db.models import Account, Conversation, Message, User
from app.db.schema import initialize_schema


def initialize():
    initialize_schema(get_engine())


def user_data(user):
    return {"id": user.id, "name": user.name} if user is not None else None


def conversation_data(conversation):
    if conversation is None:
        return None
    return {key: getattr(conversation, key) for key in ("id", "user_id", "title", "pinned")}


def create_account(email, name, password_hash):
    from uuid import uuid4

    with session() as database:
        user = User(name="account_" + uuid4().hex)
        database.add(user)
        database.flush()
        account = Account(user_id=user.id, email=email, name=name, password_hash=password_hash)
        database.add(account)
        database.flush()
        return {"id": user.id, "name": name, "email": email}


def account_by_email(email):
    with session() as database:
        account = database.scalar(select(Account).where(Account.email == email))
        if account is None:
            return None
        return {"id": account.user_id, "name": account.name, "email": account.email,
                "password_hash": account.password_hash}


def users():
    with session() as database:
        return [user_data(user) for user in database.scalars(select(User).order_by(User.name, User.id))]


def create_user(name):
    with session() as database:
        user = User(name=name)
        database.add(user)
        database.flush()
        return user_data(user)


def get_user(user_id):
    with session() as database:
        return user_data(database.get(User, user_id))


def conversations(user_id):
    with session() as database:
        query = select(Conversation).where(Conversation.user_id == user_id).order_by(
            Conversation.pinned.desc(), Conversation.id.desc()
        )
        return [conversation_data(conversation) for conversation in database.scalars(query)]


def create_conversation(user_id, title="New conversation"):
    with session() as database:
        conversation = Conversation(user_id=user_id, title=title)
        database.add(conversation)
        database.flush()
        return conversation_data(conversation)


def get_conversation(user_id, conversation_id):
    with session() as database:
        conversation = database.scalar(select(Conversation).where(
            Conversation.user_id == user_id, Conversation.id == conversation_id
        ))
        return conversation_data(conversation)


def update_conversation(user_id, conversation_id, title=None, pinned=None):
    values = {}
    if title is not None:
        values["title"] = title
    if pinned is not None:
        values["pinned"] = pinned
    if not values:
        return get_conversation(user_id, conversation_id)
    with session() as database:
        conversation = database.scalar(update(Conversation).where(
            Conversation.user_id == user_id, Conversation.id == conversation_id
        ).values(**values).returning(Conversation))
        return conversation_data(conversation)


def delete_conversation(user_id, conversation_id):
    with session() as database:
        identifier = database.scalar(delete(Conversation).where(
            Conversation.user_id == user_id, Conversation.id == conversation_id
        ).returning(Conversation.id))
        return {"id": identifier} if identifier is not None else None


def messages(user_id, limit=None, conversation_id=None):
    query = select(Message).where(Message.user_id == user_id)
    if conversation_id is not None:
        query = query.where(Message.conversation_id == conversation_id)
    query = query.order_by(Message.id if limit is None else Message.id.desc())
    if limit is not None:
        query = query.limit(limit)
    with session() as database:
        rows = [{"role": item.role, "content": item.content, "sources": item.sources}
                for item in database.scalars(query)]
        return rows if limit is None else rows[::-1]


def save_turn(user_id, question, answer, sources, conversation_id):
    with session() as database:
        database.add_all([
            Message(user_id=user_id, conversation_id=conversation_id, role="user", content=question, sources=[]),
            Message(user_id=user_id, conversation_id=conversation_id, role="assistant", content=answer, sources=sources),
        ])
