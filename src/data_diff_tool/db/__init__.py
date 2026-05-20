"""Database module - connection management and metadata queries."""

from data_diff_tool.db.connection import DWSConfig, DWSConnection, make_connection

__all__ = ["DWSConfig", "DWSConnection", "make_connection"]
