"""Settings and pool config loading."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "./config/pools.yaml"))
DB_PATH = DATA_DIR / "pool.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
# The Yahoo token is saved to DATA_DIR/.env after the one-time login.
load_dotenv(DATA_DIR / ".env")
load_dotenv()


def load_pools() -> list[dict]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"{CONFIG_PATH} not found. Copy config/pools.example.yaml to it and fill it in."
        )
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("pools", [])
