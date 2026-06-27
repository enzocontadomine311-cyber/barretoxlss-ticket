import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "storage.json")


def _load() -> dict:
    if not os.path.exists(DATA_FILE):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Setup do servidor (canal, cargo staff, categoria)
# ---------------------------------------------------------------------------

def set_guild_setup(guild_id: int, config: dict):
    data = _load()
    key = str(guild_id)
    if "setups" not in data:
        data["setups"] = {}
    data["setups"][key] = config
    _save(data)


def get_guild_setup(guild_id: int) -> dict | None:
    data = _load()
    return data.get("setups", {}).get(str(guild_id))
