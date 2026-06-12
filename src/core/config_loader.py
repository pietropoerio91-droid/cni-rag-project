from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()


class ConfigLoader:
    _instances: dict[str, dict[str, Any]] = {}

    @classmethod
    def load(cls, name: str) -> dict[str, Any]:
        if name not in cls._instances:
            config_path = Path(__file__).resolve().parent.parent.parent / "config" / f"{name}.yaml"
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
            with open(config_path, encoding="utf-8") as f:
                cls._instances[name] = yaml.safe_load(f)
        return cls._instances[name]

    @classmethod
    def get_rag_config(cls) -> dict[str, Any]:
        return cls.load("rag_config")

    @classmethod
    def get_model_config(cls) -> dict[str, Any]:
        return cls.load("model_config")

    @classmethod
    def get_qdrant_config(cls) -> dict[str, Any]:
        return cls.load("qdrant_config")

    @classmethod
    def get_logging_config(cls) -> dict[str, Any]:
        return cls.load("logging_config")
