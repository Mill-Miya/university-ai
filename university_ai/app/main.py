from __future__ import annotations

import logging
from pathlib import Path

from university_ai.app.config import AppConfig


def configure_logging(config: AppConfig) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(config.log_dir / "university_ai.log", encoding="utf-8")],
    )


def main(root: Path | None = None) -> int:
    config = AppConfig.default(root)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(config)
    logging.getLogger(__name__).info("University AI starting")
    # Phase 6 supplies the tray event loop. Keeping startup dependency-free now
    # makes database/core tests usable without a Windows desktop session.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

