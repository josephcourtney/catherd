import os
from pathlib import Path


def get_xdg_cache_dir() -> Path:
    path = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "catherd"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_xdg_config_dir() -> Path:
    path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "catherd"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_session_file(window_id: str) -> Path:
    return get_xdg_cache_dir() / f"atuin_kitty_{window_id}"
