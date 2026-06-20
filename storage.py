import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
TICKETS_FILE = os.path.join(DATA_DIR, "tickets.json")


def _ensure_file(path: str, fallback: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fallback, f, indent=2)


def _read(path: str, fallback: dict) -> dict:
    _ensure_file(path, fallback)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return fallback


def _write(path: str, data: dict):
    _ensure_file(path, {})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---- Config por servidor ----
def get_guild_config(guild_id: int) -> dict | None:
    all_configs = _read(CONFIG_FILE, {})
    return all_configs.get(str(guild_id))


def set_guild_config(guild_id: int, config: dict) -> dict:
    all_configs = _read(CONFIG_FILE, {})
    current = all_configs.get(str(guild_id), {})
    current.update(config)
    all_configs[str(guild_id)] = current
    _write(CONFIG_FILE, all_configs)
    return current


# ---- Tickets abertos ----
def get_tickets() -> dict:
    return _read(TICKETS_FILE, {})


def add_ticket(channel_id: int, ticket_data: dict):
    tickets = get_tickets()
    tickets[str(channel_id)] = ticket_data
    _write(TICKETS_FILE, tickets)


def remove_ticket(channel_id: int):
    tickets = get_tickets()
    tickets.pop(str(channel_id), None)
    _write(TICKETS_FILE, tickets)


def get_ticket(channel_id: int) -> dict | None:
    tickets = get_tickets()
    return tickets.get(str(channel_id))


def user_has_open_ticket(guild_id: int, user_id: int) -> bool:
    tickets = get_tickets()
    return any(
        t["guild_id"] == guild_id and t["user_id"] == user_id
        for t in tickets.values()
    )
