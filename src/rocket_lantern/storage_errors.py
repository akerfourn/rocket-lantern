"""Typed storage failures that can be explained before the main window opens."""

import sqlite3


class NewerDatabaseSchemaError(sqlite3.DatabaseError):
    def __init__(self, database_version: int, supported_version: int) -> None:
        self.database_version = database_version
        self.supported_version = supported_version
        super().__init__(
            f"Database schema {database_version} is newer than this application "
            f"supports ({supported_version})"
        )
