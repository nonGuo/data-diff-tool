"""Multi-database source configuration from a YAML file.

Load a ``dws_sources.yaml`` and auto-match connections by database name
extracted from table FQNs (e.g. ``edw.sdi.contract_2000`` → ``edw``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class DWSSource:
    """A single DWS database connection profile."""

    name: str
    host: str
    port: int = 8000
    user: str = ""
    password: str = ""


class SourceConfig:
    """Manage multiple DWS data sources loaded from a YAML config file."""

    def __init__(self, config_path: str | Path) -> None:
        self._path = Path(config_path)
        with open(self._path) as f:
            data = yaml.safe_load(f) or {}
        raw = data.get("sources", {})
        self._sources: dict[str, DWSSource] = {}
        for name, info in raw.items():
            self._sources[name] = DWSSource(
                name=name,
                host=info["host"],
                port=int(info.get("port", 8000)),
                user=info.get("user", ""),
                password=info.get("password", ""),
            )

    def get_source(self, db_name: str) -> DWSSource:
        """Look up a source by its key name."""
        if db_name not in self._sources:
            available = ", ".join(sorted(self._sources.keys()))
            raise ValueError(
                f"Unknown database source '{db_name}'. "
                f"Available sources: {available}"
            )
        return self._sources[db_name]

    def get_source_for_fqn(self, fqn: str) -> DWSSource:
        """Extract the database name from a FQN like 'db.schema.table' and look it up."""
        db_name = fqn.split(".")[0] if fqn else ""
        if not db_name:
            raise ValueError(f"Cannot extract database name from FQN: '{fqn}'")
        return self.get_source(db_name)

    def get_unique_sources(self, fqns: list[str]) -> dict[str, DWSSource]:
        """Return a deduplicated {db_name: source} for all FQNs."""
        result: dict[str, DWSSource] = {}
        for fqn in fqns:
            db_name = fqn.split(".")[0] if fqn else ""
            if db_name and db_name not in result:
                result[db_name] = self.get_source(db_name)
        return result

    @property
    def source_names(self) -> list[str]:
        return sorted(self._sources.keys())
