import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import attempts, hasher
from app.services.sessions import COOKIE, sessions
from tests.fake_database import mock_database


class AuthTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        attempts.clear()
        self.client = TestClient(app)
        self.database = mock_database(self)
        self.addCleanup(self.client.close)
        self.addCleanup(sessions.clear)
        self.addCleanup(attempts.clear)

    def test_registration_hashes_password_and_rotates_session(self):
        before = self.client.cookies[COOKIE]
        response = self.client.post('/api/auth/register', json={
            'name': 'Another', 'email': 'ANOTHER@example.com', 'password': 'a-strong-password'})
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(self.client.cookies[COOKIE], before)
        self.assertNotIn(before, sessions)
        account = self.database.accounts['another@example.com']
        self.assertNotIn('password_hash', response.text)
        self.assertNotEqual(account['password_hash'], 'a-strong-password')
        self.assertTrue(hasher.verify(account['password_hash'], 'a-strong-password'))
        self.assertIn('httponly', response.headers['set-cookie'].lower())
        self.assertIn('samesite=strict', response.headers['set-cookie'].lower())

    def test_logout_revokes_old_cookie_and_clears_uploads(self):
        token = self.client.cookies[COOKIE]
        self.client.post('/api/document', files={'file': ('private.txt', b'private')})
        previous = sessions[token]
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)
        self.assertEqual(previous.uploads, {})
        self.assertIsNone(previous.account)
        self.assertNotIn(token, sessions)
        self.client.cookies.set(COOKIE, token)
        self.assertEqual(self.client.get('/api/state').status_code, 401)
        self.assertIsNone(self.client.get('/api/auth/me').json()['user'])

    def test_wrong_or_missing_account_has_same_error(self):
        for email in ('tester@example.com', 'unknown@example.com'):
            response = self.client.post('/api/auth/login', json={'email': email, 'password': 'wrong'})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {'detail': 'Email or password is incorrect'})

    def test_duplicate_email_and_invalid_registration(self):
        response = self.client.post('/api/auth/register', json={
            'name': 'Tester', 'email': 'tester@example.com', 'password': 'test-password-123'})
        self.assertEqual(response.status_code, 409)
        for changes in ({'password': 'short'}, {'email': 'not-email'}, {'name': '  '}):
            response = self.client.post('/api/auth/register', json={
                'name': 'New', 'email': 'new@example.com', 'password': 'test-password-123', **changes})
            self.assertEqual(response.status_code, 422)

    def test_anonymous_api_access_is_rejected(self):
        with TestClient(app) as other:
            for method, path in [('GET', '/api/state'), ('GET', '/api/users'), ('GET', '/api/conversations'),
                                 ('GET', '/api/document/download'), ('GET', '/api/files/download')]:
                self.assertEqual(other.request(method, path).status_code, 401)
            self.assertEqual(other.post('/api/document', files={'file': ('x.txt', b'x')}).status_code, 401)

    def test_cross_site_login_and_mutation_are_rejected(self):
        for headers in ({'origin': 'https://evil.example'}, {'sec-fetch-site': 'cross-site'}):
            response = self.client.post('/api/auth/login', headers=headers, json={
                'email': 'tester@example.com', 'password': 'test-password-123'})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'origin': 'http://testserver'}).status_code, 200)

    def test_attempts_are_rate_limited(self):
        for _ in range(9):
            self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'wrong'})
        response = self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'wrong'})
        self.assertEqual(response.status_code, 429)

    def test_legacy_profiles_cannot_be_claimed(self):
        legacy = self.database.create_user('Legacy')
        self.client.post('/api/auth/register', json={
            'name': 'Legacy', 'email': 'legacy@example.com', 'password': 'test-password-123'})
        self.assertNotEqual(self.client.get('/api/auth/me').json()['user']['id'], legacy['id'])
        self.assertEqual(self.client.post(f'/api/users/{legacy["id"]}/select').status_code, 403)
