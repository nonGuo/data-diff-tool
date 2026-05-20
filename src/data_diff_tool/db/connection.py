"""Database connection management for DWS.

Supports three ways to configure the connection:

1. DSN string:    ``postgresql://user:pass@host:port/dbname``
2. Individual kwargs: ``DWSConfig(host=..., port=..., dbname=..., user=..., password=...)``
3. Environment variables: ``DWS_HOST``, ``DWS_PORT``, ``DWS_DBNAME``, ``DWS_USER``, ``DWS_PASSWORD``

Priority: DSN > kwargs > environment variables.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator
from urllib.parse import urlparse

import psycopg2
from psycopg2.extensions import connection
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8000
DEFAULT_POOL_MIN = 1
DEFAULT_POOL_MAX = 10


def _env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable."""
    return os.environ.get(name, default)


@dataclass
class DWSConfig:
    """Holds all connection configuration with layered resolution."""

    dsn: str | None = None
    host: str | None = None
    port: int | None = None
    dbname: str | None = None
    user: str | None = None
    password: str | None = None
    pool_min: int = DEFAULT_POOL_MIN
    pool_max: int = DEFAULT_POOL_MAX
    connect_timeout: int = 10

    @classmethod
    def from_kwargs(
        cls,
        *,
        dsn: str | None = None,
        host: str | None = None,
        port: int | None = None,
        dbname: str | None = None,
        user: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> DWSConfig:
        """Build config from explicit kwargs, falling back to env vars."""
        return cls(
            dsn=dsn,
            host=host or _env("DWS_HOST"),
            port=port or int(_env("DWS_PORT") or 0) or None,
            dbname=dbname or _env("DWS_DBNAME") or _env("DWS_DATABASE"),
            user=user or _env("DWS_USER"),
            password=password or _env("DWS_PASSWORD"),
            **kwargs,
        )

    def resolve(self) -> dict[str, Any]:
        """
        Resolve final connection parameters.

        If a DSN is provided, it takes priority.
        Otherwise, individual parameters are used.
        """
        if self.dsn:
            return {"dsn": self.dsn}

        params: dict[str, Any] = {}
        if self.host:
            params["host"] = self.host
        if self.port:
            params["port"] = self.port
        else:
            params["port"] = DEFAULT_PORT
        if self.dbname:
            params["dbname"] = self.dbname
        if self.user:
            params["user"] = self.user
        if self.password:
            params["password"] = self.password
        if self.connect_timeout:
            params["connect_timeout"] = self.connect_timeout

        return params

    def validate(self) -> None:
        """Validate that enough information is present to connect."""
        if self.dsn:
            return

        missing = []
        if not self.host:
            missing.append("host")
        if not self.dbname:
            missing.append("dbname")
        if not self.user:
            missing.append("user")
        if not self.password:
            missing.append("password")

        if missing:
            raise ValueError(
                f"Missing required connection parameters: {', '.join(missing)}. "
                f"Provide them via CLI arguments or environment variables "
                f"(DWS_HOST, DWS_DBNAME, DWS_USER, DWS_PASSWORD)."
            )

    def masked_repr(self) -> str:
        """Return a representation with the password hidden."""
        if self.dsn:
            parsed = urlparse(self.dsn)
            if parsed.password:
                safe = self.dsn.replace(parsed.password, "****")
            else:
                safe = self.dsn
            return safe

        parts = []
        if self.host:
            parts.append(f"host={self.host}")
        parts.append(f"port={self.port or DEFAULT_PORT}")
        if self.dbname:
            parts.append(f"dbname={self.dbname}")
        if self.user:
            parts.append(f"user={self.user}")
        parts.append("password=****")
        return " ".join(parts)

    @classmethod
    def from_source(cls, source: Any, dbname: str | None = None) -> DWSConfig:
        """Build DWSConfig from a DWSSource object."""
        return cls(
            host=source.host,
            port=source.port,
            dbname=dbname,
            user=source.user,
            password=source.password,
        )


class DWSConnection:
    """Manages a connection pool to DWS database."""

    def __init__(self, config: DWSConfig) -> None:
        self.config = config
        self.config.validate()
        self._pool: SimpleConnectionPool | None = None

    def connect(self) -> None:
        """Initialize the connection pool."""
        params = self.config.resolve()
        logger.info("Connecting to DWS: %s", self.config.masked_repr())
        self._pool = SimpleConnectionPool(
            minconn=self.config.pool_min,
            maxconn=self.config.pool_max,
            **params,
        )
        # Test the connection
        with self.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()
            logger.info("Connected to DWS: %s", version[0] if version else "unknown")

    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            logger.info("DWS connection pool closed")

    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        """Provide a transactional cursor from the connection pool."""
        if not self._pool:
            self.connect()

        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    @property
    def pool(self) -> SimpleConnectionPool | None:
        """Return the underlying connection pool."""
        return self._pool


def make_connection(
    *,
    dsn: str | None = None,
    host: str | None = None,
    port: int | None = None,
    dbname: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> DWSConnection:
    """
    Factory function to create a DWSConnection.

    Convenience wrapper that builds a DWSConfig and returns a connection.
    """
    config = DWSConfig.from_kwargs(
        dsn=dsn,
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )
    return DWSConnection(config)
