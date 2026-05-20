"""Tests for database connection and configuration."""

import os
from unittest import mock

import pytest

from data_diff_tool.db.connection import DWSConfig, DWSConnection, make_connection


class TestDWSConfigFromKwargs:
    def test_basic_kwargs(self):
        config = DWSConfig.from_kwargs(
            host="dws.example.com", port=8000, dbname="edw", user="admin", password="secret"
        )
        params = config.resolve()
        assert params == {
            "host": "dws.example.com",
            "port": 8000,
            "dbname": "edw",
            "user": "admin",
            "password": "secret",
            "connect_timeout": 10,
        }

    def test_dsn_takes_priority(self):
        config = DWSConfig.from_kwargs(
            dsn="postgresql://user:pass@host:5432/mydb",
            host="other.example.com",
            user="other",
        )
        params = config.resolve()
        assert params == {"dsn": "postgresql://user:pass@host:5432/mydb"}

    def test_port_defaults_to_8000(self):
        config = DWSConfig.from_kwargs(
            host="dws.example.com", dbname="edw", user="admin", password="secret"
        )
        params = config.resolve()
        assert params["port"] == 8000


class TestDWSConfigFromEnv:
    def test_env_vars(self):
        env = {
            "DWS_HOST": "env-host",
            "DWS_PORT": "9000",
            "DWS_DBNAME": "env-db",
            "DWS_USER": "env-user",
            "DWS_PASSWORD": "env-pass",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = DWSConfig.from_kwargs()
            params = config.resolve()
            assert params["host"] == "env-host"
            assert params["port"] == 9000
            assert params["dbname"] == "env-db"
            assert params["user"] == "env-user"
            assert params["password"] == "env-pass"

    def test_kwargs_override_env(self):
        env = {
            "DWS_HOST": "env-host",
            "DWS_PORT": "9000",
            "DWS_DBNAME": "env-db",
            "DWS_USER": "env-user",
            "DWS_PASSWORD": "env-pass",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = DWSConfig.from_kwargs(host="override-host")
            assert config.host == "override-host"


class TestDWSConfigValidate:
    def test_valid_dsn(self):
        config = DWSConfig.from_kwargs(dsn="postgresql://u:p@h:5432/db")
        config.validate()  # should not raise

    def test_valid_kwargs(self):
        config = DWSConfig.from_kwargs(host="h", dbname="db", user="u", password="p")
        config.validate()  # should not raise

    def test_missing_host(self):
        config = DWSConfig.from_kwargs(dbname="db", user="u", password="p")
        with pytest.raises(ValueError, match="host"):
            config.validate()

    def test_missing_user(self):
        config = DWSConfig.from_kwargs(host="h", dbname="db", password="p")
        with pytest.raises(ValueError, match="user"):
            config.validate()

    def test_missing_multiple(self):
        config = DWSConfig.from_kwargs()
        with pytest.raises(ValueError, match="host, dbname, user, password"):
            config.validate()


class TestDWSConfigMaskedRepr:
    def test_dsn_masked(self):
        config = DWSConfig.from_kwargs(dsn="postgresql://admin:secret123@host:5432/edw")
        assert "secret123" not in config.masked_repr()
        assert "****" in config.masked_repr()

    def test_kwargs_masked(self):
        config = DWSConfig.from_kwargs(host="host", dbname="edw", user="admin", password="secret123")
        repr_str = config.masked_repr()
        assert "secret123" not in repr_str
        assert "password=****" in repr_str


class TestMakeConnection:
    def test_factory_with_dsn(self):
        conn = make_connection(dsn="postgresql://u:p@host:5432/db")
        assert isinstance(conn, DWSConnection)
        assert conn.config.dsn == "postgresql://u:p@host:5432/db"

    def test_factory_with_kwargs(self):
        conn = make_connection(host="host", port=8000, dbname="db", user="u", password="p")
        assert conn.config.host == "host"
        assert conn.config.port == 8000
