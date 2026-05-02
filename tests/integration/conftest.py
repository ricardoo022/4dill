"""Shared integration fixtures across integration subpackages."""

from tests.integration.database.conftest import db_schema, db_session

__all__ = ["db_schema", "db_session"]
