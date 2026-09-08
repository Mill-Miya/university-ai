from university_ai.app.config import AppConfig
from university_ai.app.main import main


def test_config_uses_separate_data_and_log_directories(tmp_path):
    config = AppConfig.default(tmp_path)
    assert config.database_path == tmp_path / "data" / "university_ai.sqlite3"
    assert config.log_dir == tmp_path / "logs"


def test_startup_creates_application_directories(tmp_path):
    assert main(tmp_path) == 0
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "logs" / "university_ai.log").is_file()
