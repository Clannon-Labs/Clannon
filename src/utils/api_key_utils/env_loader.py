from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def init_env() -> None:
    current = Path(__file__).resolve().parent

    while current != current.parent:
        env_files = list(current.glob(".env*"))

        if env_files:
            for env_file in env_files:
                load_dotenv(env_file, override=True)
            break

        current = current.parent
