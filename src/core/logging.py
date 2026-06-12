import logging.config
from pathlib import Path

import yaml


def setup_logging(config_path: str | None = None) -> None:
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "logging_config.yaml"

    config_path = Path(config_path)
    if not config_path.exists():
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        return

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    for handler_config in config.get("handlers", {}).values():
        filename = handler_config.get("filename")
        if filename:
            handler_config["filename"] = str(Path(filename).resolve())

    logging.config.dictConfig(config)
