import os
import unittest
from unittest.mock import Mock, patch

from psycopg.conninfo import conninfo_to_dict

from app.db.connection import database_url, dispose_engine, get_engine, session


class DatabaseTests(unittest.TestCase):
    def test_original_url_is_preserved(self):
        url = "postgresql://demo:example@127.0.0.1:5432/chatbot?sslmode=prefer"
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
            self.assertEqual(database_url(), url)

    def test_container_overrides_preserve_credentials_and_options(self):
        settings = {
            "DATABASE_URL": "postgresql://demo:p%40ss@127.0.0.1:15432/chatbot?sslmode=prefer",
            "DATABASE_HOST": "db",
            "DATABASE_PORT": "5432",
        }
        with patch.dict(os.environ, settings, clear=True):
            config = conninfo_to_dict(database_url())
        self.assertEqual(config["host"], "db")
        self.assertEqual(config["port"], "5432")
        self.assertEqual(config["user"], "demo")
        self.assertEqual(config["password"], "p@ss")
        self.assertEqual(config["dbname"], "chatbot")
        self.assertEqual(config["sslmode"], "prefer")

    def test_postgres_settings_without_url(self):
        settings = {
            "DATABASE_URL": "",
            "DATABASE_HOST": "db",
            "DATABASE_PORT": "5432",
            "POSTGRES_USER": "demo",
            "POSTGRES_PASSWORD": "p@ss word:'\\secret",
            "POSTGRES_DB": "demo_db",
        }
        with patch.dict(os.environ, settings, clear=True):
            config = conninfo_to_dict(database_url())
        self.assertEqual(config["host"], "db")
        self.assertEqual(config["port"], "5432")
        self.assertEqual(config["user"], "demo")
        self.assertEqual(config["password"], settings["POSTGRES_PASSWORD"])
        self.assertEqual(config["dbname"], "demo_db")

    def test_postgres_defaults_for_local_connection(self):
        with patch.dict(os.environ, {"POSTGRES_PASSWORD": "example"}, clear=True):
            config = conninfo_to_dict(database_url())
        self.assertEqual(config["host"], "127.0.0.1")
        self.assertEqual(config["port"], "5432")
        self.assertEqual(config["user"], "chatbot")
        self.assertEqual(config["dbname"], "chatbot")

    def test_url_takes_priority_over_postgres_settings(self):
        url = "postgresql://demo:example@127.0.0.1:5432/existing"
        with patch.dict(os.environ, {
            "DATABASE_URL": url,
            "POSTGRES_USER": "other",
            "POSTGRES_PASSWORD": "other",
            "POSTGRES_DB": "other",
        }, clear=True):
            self.assertEqual(database_url(), url)

    def test_engine_is_lazy_pooled_and_disposed(self):
        dispose_engine()
        self.addCleanup(dispose_engine)
        with patch.dict(os.environ, {"POSTGRES_PASSWORD": "example"}, clear=True), patch(
            "app.db.connection.psycopg.connect"
        ) as connect:
            engine = get_engine()
            self.assertIs(get_engine(), engine)
            self.assertEqual(engine.dialect.driver, "psycopg")
            self.assertTrue(engine.pool._pre_ping)
            self.assertTrue(engine.hide_parameters)
            connect.assert_not_called()
            with patch.object(engine, "dispose") as dispose:
                dispose_engine()
                dispose.assert_called_once_with()
        self.assertEqual(get_engine.cache_info().currsize, 0)

    def test_session_uses_transaction_and_closes(self):
        engine = Mock()
        with patch("app.db.connection.get_engine", return_value=engine), patch(
            "app.db.connection.Session"
        ) as constructor:
            database = constructor.return_value.__enter__.return_value
            with session() as active:
                self.assertIs(active, database)
            constructor.assert_called_once_with(engine)
            database.begin.assert_called_once_with()
            database.begin.return_value.__exit__.assert_called_once_with(None, None, None)
            constructor.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_missing_url_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                database_url()


if __name__ == "__main__":
    unittest.main()
