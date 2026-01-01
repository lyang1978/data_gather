import os
from dotenv import load_dotenv

_DOTENV_LOADED = False

def load_env() -> None:
    global _DOTENV_LOADED
    if not _DOTENV_LOADED:
        load_dotenv()  # reads .env from project root
        _DOTENV_LOADED = True

def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val
