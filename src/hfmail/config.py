import json
import os
from pathlib import Path

DEFAULT_RUNS_DIR = Path.home() / "runs" / "hfmail"
CONFIG_PATH = DEFAULT_RUNS_DIR / "config.json"
DB_PATH = DEFAULT_RUNS_DIR / "mail.db"

DEFAULT_CONFIG = {
    "incoming_smtp": {
        "host": "127.0.0.1",
        "port": 1025
    },
    "incoming_imap": {
        "host": "",
        "port": 993,
        "username": "",
        "password": "",
        "use_ssl": True,
        "folder": "INBOX",
        "delete_from_server": True
    },
    "outgoing_smtp": {
        "host": "",
        "port": 587,
        "username": "",
        "password": "",
        "use_tls": True,
        "from_address": ""  # Address to send unsubscribe emails from
    },
    "auto_unsubscribe": True,  # If True, automatically unsubscribes promotions/newsletters on arrival
    "only_huggingface": True   # If True, automatically marks non-HuggingFace mail as spam
}

def ensure_dirs():
    DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            user_config = json.load(f)
            # Merge with default config to ensure all keys exist
            merged = DEFAULT_CONFIG.copy()
            for k, v in user_config.items():
                if isinstance(v, dict) and k in merged:
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    except Exception:
        return DEFAULT_CONFIG

def save_config(config):
    ensure_dirs()
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def get_db_path():
    ensure_dirs()
    return DB_PATH
