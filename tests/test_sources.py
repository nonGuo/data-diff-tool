"""Tests for multi-database source configuration."""

import os
import tempfile

from data_diff_tool.db.sources import DWSSource, SourceConfig


SAMPLE_YAML = """\
sources:
  edw:
    host: 10.0.1.100
    port: 8000
    user: admin
    password: secret123
  ods:
    host: 10.0.2.200
    user: readonly
    password: pass456
"""


class TestSourceConfig:
    def test_load_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        assert cfg.source_names == ["edw", "ods"]

    def test_get_source_by_name(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        src = cfg.get_source("edw")
        assert src.name == "edw"
        assert src.host == "10.0.1.100"
        assert src.port == 8000
        assert src.user == "admin"
        assert src.password == "secret123"

    def test_default_port(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        # ods has no port specified, should default to 8000
        src = cfg.get_source("ods")
        assert src.port == 8000

    def test_unknown_source_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        import pytest
        with pytest.raises(ValueError, match="Unknown database source"):
            cfg.get_source("nonexistent")

    def test_get_source_for_fqn(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        src = cfg.get_source_for_fqn("edw.sdi.contract_2000")
        assert src.name == "edw"
        assert src.host == "10.0.1.100"

    def test_get_source_for_fqn_invalid(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        import pytest
        with pytest.raises(ValueError, match="Cannot extract database name"):
            cfg.get_source_for_fqn("")

    def test_get_unique_sources_dedup(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        fqns = [
            "edw.sdi.contract_2000",
            "edw.sdi.order_2000",
            "ods.sdi.user_2000",
        ]
        unique = cfg.get_unique_sources(fqns)
        assert set(unique.keys()) == {"edw", "ods"}
        assert unique["edw"].host == "10.0.1.100"
        assert unique["ods"].host == "10.0.2.200"

    def test_empty_fqns(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        unique = cfg.get_unique_sources([])
        assert unique == {}

    def test_fqn_unknown_db_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            cfg = SourceConfig(f.name)
        import pytest
        with pytest.raises(ValueError, match="Unknown database source"):
            cfg.get_source_for_fqn("missing.sdi.table")


class TestDWSSource:
    def test_defaults(self):
        src = DWSSource(name="test", host="localhost")
        assert src.port == 8000
        assert src.user == ""
        assert src.password == ""
