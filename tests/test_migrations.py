from university_ai.database.database import Database
from university_ai.database.migrations import migrate


def test_migrations_are_idempotent(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    connection = database.connect()
    migrate(connection)
    migrate(connection)
    assert connection.execute("SELECT version FROM schema_version").fetchone()[0] == 2
    database.stop()
