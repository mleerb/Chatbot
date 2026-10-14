from unittest.mock import patch


class FakeDatabase:
    def __init__(self):
        self.people = {}
        self.turns = {}

    def users(self):
        return list(self.people.values())

    def create_user(self, name):
        user = {"id": len(self.people) + 1, "name": name}
        self.people[user["id"]] = user
        self.turns[user["id"]] = []
        return user

    def get_user(self, user_id):
        return self.people.get(user_id)

    def messages(self, user_id, limit=None):
        items = self.turns[user_id]
        return list(items[-limit:] if limit else items)

    def save_turn(self, user_id, question, answer, sources):
        self.turns[user_id].extend([
            {"role": "user", "content": question, "sources": []},
            {"role": "assistant", "content": answer, "sources": sources},
        ])


def mock_database(test):
    database = FakeDatabase()
    patches = [patch(f"app.database.{name}", getattr(database, name)) for name in
               ("users", "create_user", "get_user", "messages", "save_turn")]
    patches.append(patch("app.database.initialize"))
    for item in patches:
        item.start()
        test.addCleanup(item.stop)
    test.client.post('/api/users', json={'name': 'Tester'})
    test.client.post('/api/users/1/select')
    return database
