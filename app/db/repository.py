from sqlalchemy import delete, select, update

from app.db.connection import get_engine, session
from app.db.models import Account, ChatFile, Conversation, Message, User
from app.db.schema import initialize_schema


DEFAULT_TITLE = "New conversation"


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


def create_conversation(user_id, title=DEFAULT_TITLE):
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
        rows = [{"role": item.role, "content": item.content, "sources": item.sources,
                 "attachments": item.attachments} for item in database.scalars(query)]
        return rows if limit is None else rows[::-1]


def save_turn(user_id, question, answer, sources, conversation_id, attachments=()):
    with session() as database:
        database.add_all([
            Message(user_id=user_id, conversation_id=conversation_id, role="user", content=question, sources=[],
                    attachments=list(attachments)),
            Message(user_id=user_id, conversation_id=conversation_id, role="assistant", content=answer, sources=sources),
        ])


def attached_file_ids(user_id, conversation_id):
    query = select(Message.attachments).where(
        Message.user_id == user_id, Message.conversation_id == conversation_id, Message.role == "user"
    )
    with session() as database:
        return {item["id"] for attachments in database.scalars(query) for item in attachments}


def file_data(item):
    return {key: getattr(item, key) for key in (
        "file_id", "parent_id", "kind", "filename", "data", "document", "image_url", "status", "pages",
    )}


def save_file(user_id, conversation_id, kind, file_id, filename, data, document="", image_url="", status="",
              pages=(), parent_id=None):
    with session() as database:
        database.add(ChatFile(
            user_id=user_id, conversation_id=conversation_id, kind=kind, file_id=file_id, filename=filename,
            data=data, document=document, image_url=image_url, status=status, pages=[list(page) for page in pages],
            parent_id=parent_id,
        ))


def update_file_text(user_id, file_id, document, image_url, status, pages):
    with session() as database:
        database.execute(update(ChatFile).where(ChatFile.user_id == user_id, ChatFile.file_id == file_id).values(
            document=document, image_url=image_url, status=status, pages=[list(page) for page in pages]))


def conversation_files(user_id, conversation_id):
    query = select(ChatFile).where(
        ChatFile.user_id == user_id, ChatFile.conversation_id == conversation_id
    ).order_by(ChatFile.id)
    with session() as database:
        return [file_data(item) for item in database.scalars(query)]


def delete_files(user_id, conversation_id, file_id=None):
    query = delete(ChatFile).where(ChatFile.user_id == user_id, ChatFile.conversation_id == conversation_id)
    if file_id is None:
        query = query.where(ChatFile.kind.in_(("upload", "revision")))
    else:
        query = query.where((ChatFile.file_id == file_id) | (ChatFile.parent_id == file_id))
    with session() as database:
        database.execute(query)
