from pathlib import Path

from tg_bot.config import Settings


def test_local_bot_looks_for_project_env_before_package_env():
    root = Path(__file__).resolve().parents[2]
    assert Settings.model_config["env_file"] == (root / ".env", root / "tg_bot" / ".env")
