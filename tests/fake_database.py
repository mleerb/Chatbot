from unittest.mock import patch


class FakeDatabase:
    def __init__(self):
        self.people = {}
        self.turns = {}
        self.chats = {}
        self.next_chat = 1
        self.accounts = {}

    def create_account(self, email, name, password_hash):
        if email in self.accounts:
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError("insert", {}, Exception("duplicate"))
        user = self.create_user(name)
        self.accounts[email] = {**user, "email": email, "password_hash": password_hash}
        return {**user, "email": email}

    def account_by_email(self, email):
        return self.accounts.get(email)

    def users(self):
        return list(self.people.values())

    def create_user(self, name):
        user = {"id": len(self.people) + 1, "name": name}
        self.people[user["id"]] = user
        self.turns[user["id"]] = []
        return user

    def get_user(self, user_id):
        return self.people.get(user_id)

    def conversations(self, user_id):
        return sorted((item for item in self.chats.values() if item['user_id'] == user_id),
                      key=lambda item: (item['pinned'], item['id']), reverse=True)

    def create_conversation(self, user_id, title='New conversation'):
        chat = {'id': self.next_chat, 'user_id': user_id, 'title': title, 'pinned': False}
        self.next_chat += 1
        self.chats[chat['id']] = chat
        return chat

    def get_conversation(self, user_id, conversation_id):
        chat = self.chats.get(conversation_id)
        return chat if chat and chat['user_id'] == user_id else None

    def update_conversation(self, user_id, conversation_id, title=None, pinned=None):
        chat = self.get_conversation(user_id, conversation_id)
        if chat is not None:
            if title is not None:
                chat['title'] = title
            if pinned is not None:
                chat['pinned'] = pinned
        return chat

    def delete_conversation(self, user_id, conversation_id):
        chat = self.get_conversation(user_id, conversation_id)
        if chat is not None:
            del self.chats[conversation_id]
            self.turns[user_id] = [item for item in self.turns[user_id]
                                   if item['conversation_id'] != conversation_id]
        return chat

    def messages(self, user_id, limit=None, conversation_id=None):
        items = [item for item in self.turns[user_id]
                 if conversation_id is None or item['conversation_id'] == conversation_id]
        return [{key: value for key, value in item.items() if key != 'conversation_id'}
                for item in (items[-limit:] if limit else items)]

    def save_turn(self, user_id, question, answer, sources, conversation_id):
        self.turns[user_id].extend([
            {"role": "user", "content": question, "sources": [], "conversation_id": conversation_id},
            {"role": "assistant", "content": answer, "sources": sources, "conversation_id": conversation_id},
        ])


def mock_database(test):
    database = FakeDatabase()
    patches = [patch(f"app.db.repository.{name}", getattr(database, name)) for name in
               ("create_account", "account_by_email", "users", "create_user", "get_user", "messages", "save_turn", "conversations",
                "create_conversation", "get_conversation", "update_conversation", "delete_conversation")]
    patches.append(patch("app.db.repository.initialize"))
    for item in patches:
        item.start()
        test.addCleanup(item.stop)
    from app.services.auth import attempts
    attempts.clear()
    test.client.post('/api/auth/register', json={
        'name': 'Tester', 'email': 'tester@example.com', 'password': 'test-password-123'})
    test.client.post('/api/users/1/select')
    return database
