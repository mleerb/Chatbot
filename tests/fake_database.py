from unittest.mock import patch


class FakeDatabase:
    def __init__(self):
        self.people = {}
        self.turns = {}
        self.chats = {}
        self.next_chat = 1
        self.accounts = {}
        self.files = {}
        self.usages = {}

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
            self.files = {key: item for key, item in self.files.items() if item['conversation_id'] != conversation_id}
        return chat

    def messages(self, user_id, limit=None, conversation_id=None):
        items = [item for item in self.turns[user_id]
                 if conversation_id is None or item['conversation_id'] == conversation_id]
        return [{key: value for key, value in item.items() if key != 'conversation_id'}
                for item in (items[-limit:] if limit else items)]

    def save_turn(self, user_id, question, answer, sources, conversation_id, attachments=(), answer_attachments=(),
                  stopped=False, trace_id=None, replace_from=None):
        if replace_from is not None:
            items = [item for item in self.turns[user_id] if item['conversation_id'] == conversation_id]
            if replace_from >= len(items) or items[replace_from]['role'] != 'user':
                raise LookupError('Message not found')
            removed = {id(item) for item in items[replace_from:]}
            self.turns[user_id] = [item for item in self.turns[user_id] if id(item) not in removed]
        self.turns[user_id].extend([
            {"role": "user", "content": question, "sources": [], "attachments": list(attachments),
             "stopped": False, "rating": None, "trace_id": None, "conversation_id": conversation_id},
            {"role": "assistant", "content": answer, "sources": sources, "attachments": list(answer_attachments),
             "stopped": stopped, "rating": None, "trace_id": trace_id, "conversation_id": conversation_id},
        ])

    def rate_message(self, user_id, conversation_id, index, rating):
        items = [item for item in self.turns.get(user_id, []) if item['conversation_id'] == conversation_id]
        if not 0 <= index < len(items) or items[index]['role'] != 'assistant':
            return None
        items[index]['rating'] = rating
        return {'trace_id': items[index]['trace_id']}

    def attached_file_ids(self, user_id, conversation_id):
        return {item["id"] for turn in self.turns.get(user_id, []) if turn["conversation_id"] == conversation_id
                for item in turn["attachments"]}

    def check_upload_capacity(self, user_id, conversation_id, size):
        from app.core.limits import check_upload

        items = [item for item in self.files.values() if item["user_id"] == user_id
                 and item["conversation_id"] == conversation_id and item["kind"] == "upload"]
        check_upload(size, len(items), sum(len(item["data"]) for item in items))

    def save_file(self, user_id, conversation_id, kind, file_id, filename, data, document="", image_url="", status="",
                  pages=(), parent_id=None, embeddings=None):
        if kind == "upload":
            self.check_upload_capacity(user_id, conversation_id, len(data))
        self.files[file_id] = {
            "user_id": user_id, "conversation_id": conversation_id, "file_id": file_id, "parent_id": parent_id,
            "kind": kind, "filename": filename, "data": data, "document": document, "image_url": image_url,
            "status": status, "pages": [list(page) for page in pages], "embeddings": embeddings,
        }

    def update_file_text(self, user_id, file_id, document, image_url, status, pages, embeddings=None):
        item = self.files.get(file_id)
        if item and item["user_id"] == user_id:
            item.update(document=document, image_url=image_url, status=status, pages=[list(page) for page in pages],
                        embeddings=embeddings)

    def update_file_embeddings(self, user_id, conversation_id, file_id, document, embeddings):
        item = self.files.get(file_id)
        if item and (item["user_id"], item["conversation_id"], item["document"]) == (user_id, conversation_id, document):
            item["embeddings"] = embeddings
            return 1
        return 0

    def conversation_files(self, user_id, conversation_id):
        return [{key: value for key, value in item.items() if key not in ("user_id", "conversation_id")}
                for item in self.files.values()
                if item["user_id"] == user_id and item["conversation_id"] == conversation_id]

    def delete_files(self, user_id, conversation_id, file_id=None):
        for key, item in list(self.files.items()):
            if item["user_id"] != user_id or item["conversation_id"] != conversation_id:
                continue
            if (item["kind"] != "generated" if file_id is None else file_id in (item["file_id"], item["parent_id"])):
                del self.files[key]

    def usage(self, user_id):
        item = self.usages.get(user_id)
        return dict(item) if item else None

    def add_usage(self, user_id, tokens, day_start):
        item = self.usages.get(user_id)
        if item and item["window_start"] >= day_start:
            item["tokens"] += tokens
        else:
            self.usages[user_id] = {"tokens": tokens, "uploads": 0, "images": 0, "window_start": day_start}

    def add_count(self, user_id, name, day_start, limit):
        item = self.usages.get(user_id)
        if item is None or item["window_start"] < day_start:
            item = self.usages[user_id] = {"tokens": 0, "uploads": 0, "images": 0, "window_start": day_start}
        if item[name] >= limit:
            return False
        item[name] += 1
        return True

    def remove_count(self, user_id, name, day_start):
        item = self.usages.get(user_id)
        if item and item["window_start"] >= day_start and item[name] > 0:
            item[name] -= 1


def mock_database(test):
    database = FakeDatabase()
    patches = [patch(f"app.db.repository.{name}", getattr(database, name)) for name in
               ("create_account", "account_by_email", "users", "create_user", "get_user", "messages", "save_turn", "rate_message", "conversations",
                "create_conversation", "get_conversation", "update_conversation", "delete_conversation",
                "save_file", "check_upload_capacity", "update_file_text", "update_file_embeddings", "conversation_files", "delete_files", "attached_file_ids",
                "usage", "add_usage", "add_count", "remove_count")]
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
