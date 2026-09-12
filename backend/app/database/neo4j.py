"""Phase 4 — Neo4j connection/service layer.

Configuration comes only from environment variables; nothing is hardcoded
and credentials never appear in logs or API responses::

    NEO4J_URI        e.g. bolt://localhost:7687 (default; honors
                     NEO4J_BOLT_PORT for docker-compose parity)
    NEO4J_USERNAME   (fallback: NEO4J_USER, then "neo4j")
    NEO4J_PASSWORD   required — missing value is a startup-clear 500
    NEO4J_DATABASE   default "neo4j"

The ``neo4j`` driver is imported lazily so this module (and the whole app)
imports cleanly where the driver is absent; connection attempts then fail
with an explicit structured error instead of an ImportError traceback.
"""

from __future__ import annotations

import contextlib
import os
import re

from ..services.validation import IngestionError

QUERY_TIMEOUT_SECONDS = 10.0


class Neo4jConfigError(IngestionError):
    def __init__(self, message: str) -> None:
        super().__init__("NEO4J_CONFIG_ERROR", message, http_status=500)


class Neo4jUnavailable(IngestionError):
    def __init__(self, message: str) -> None:
        super().__init__("NEO4J_UNAVAILABLE", message, http_status=503)


def _redact(text: str) -> str:
    """Strip any embedded credentials before a message leaves this module."""
    return re.sub(r"://[^/@]*@", "://***@", str(text))


class Neo4jConfig:
    def __init__(self, uri: str, username: str, password: str,
                 database: str) -> None:
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Neo4jConfig":
        env = env if env is not None else os.environ
        bolt_port = env.get("NEO4J_BOLT_PORT", "7687")
        uri = env.get("NEO4J_URI") or f"bolt://localhost:{bolt_port}"
        username = env.get("NEO4J_USERNAME") or env.get("NEO4J_USER") or "neo4j"
        password = env.get("NEO4J_PASSWORD")
        if not password:
            raise Neo4jConfigError(
                "NEO4J_PASSWORD is not set. Copy .env.example to .env and "
                "fill in a local-only password (never commit it).")
        database = env.get("NEO4J_DATABASE", "neo4j")
        return cls(uri=uri, username=username, password=password,
                   database=database)

    def describe(self) -> dict:
        """Log/API-safe description — never includes the password."""
        return {"uri": self.uri, "username": self.username,
                "database": self.database}


class Neo4jService:
    """Thin wrapper around the official driver: sessions, health checks,
    and schema bootstrap. Accepts any session factory with a compatible
    ``session()`` for tests (see backend/tests/fakes.py)."""

    def __init__(self, config: Neo4jConfig, driver=None) -> None:
        self.config = config
        self._driver = driver

    def _driver_or_connect(self):
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise Neo4jUnavailable(
                "The 'neo4j' driver package is not installed.") from exc
        try:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password))
            self._driver.verify_connectivity()
        except Exception as exc:
            raise Neo4jUnavailable(
                f"Neo4j unavailable at {self.config.uri}: "
                f"{_redact(str(exc) or type(exc).__name__)}") from exc
        return self._driver

    def verify(self) -> dict:
        """Connectivity probe. Raises Neo4jUnavailable on any failure."""
        driver = self._driver_or_connect()
        try:
            driver.verify_connectivity()
        except Exception as exc:
            raise Neo4jUnavailable(
                f"Neo4j unavailable at {self.config.uri}: "
                f"{_redact(str(exc) or type(exc).__name__)}") from exc
        return {"ok": True, **self.config.describe()}

    @contextlib.contextmanager
    def session(self):
        """Yield a driver session bound to the configured database."""
        driver = self._driver_or_connect()
        session = driver.session(database=self.config.database)
        try:
            yield session
        finally:
            session.close()

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            finally:
                self._driver = None
