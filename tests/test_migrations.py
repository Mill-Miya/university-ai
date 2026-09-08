from university_ai.database.database import Database
from university_ai.database.migrations import migrate


def test_migrations_are_idempotent(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    connection = database.connect()
    migrate(connection)
    migrate(connection)
    assert connection.execute("SELECT version FROM schema_version").fetchone()[0] == 4
    assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'").fetchone()[0] == "documents"
    assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='screen_captures'").fetchone()[0] == "screen_captures"
    database.stop()
