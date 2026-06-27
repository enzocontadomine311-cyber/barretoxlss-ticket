import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
TICKETS_FILE = os.path.join(DATA_DIR, "tickets.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")


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


# ---------------------------------------------------------------------------
# Config de produtos — chave: "guild_id:message_id"
# ---------------------------------------------------------------------------

def set_guild_config(guild_id: int, message_id: int, config: dict):
    all_configs = _read(CONFIG_FILE, {})
    key = f"{guild_id}:{message_id}"
    all_configs[key] = config
    _write(CONFIG_FILE, all_configs)


def get_config_by_message(guild_id: int, message_id: int) -> dict | None:
    all_configs = _read(CONFIG_FILE, {})
    key = f"{guild_id}:{message_id}"
    return all_configs.get(key)


# ---------------------------------------------------------------------------
# Solicitações pendentes — chave: "guild_id:user_id"
# ---------------------------------------------------------------------------

def add_pending(user_id: int, guild_id: int, data: dict):
    pending = _read(PENDING_FILE, {})
    key = f"{guild_id}:{user_id}"
    pending[key] = data
    _write(PENDING_FILE, pending)


def update_pending(user_id: int, guild_id: int, extra: dict):
    pending = _read(PENDING_FILE, {})
    key = f"{guild_id}:{user_id}"
    if key in pending:
        pending[key].update(extra)
        _write(PENDING_FILE, pending)


def get_pending_by_confirm_msg(guild_id: int, confirm_msg_id: int) -> dict | None:
    pending = _read(PENDING_FILE, {})
    for key, data in pending.items():
        if data.get("guild_id") == guild_id and data.get("confirm_msg_id") == confirm_msg_id:
            return data
    return None


def remove_pending(user_id: int, guild_id: int):
    pending = _read(PENDING_FILE, {})
    key = f"{guild_id}:{user_id}"
    pending.pop(key, None)
    _write(PENDING_FILE, pending)


# ---------------------------------------------------------------------------
# Tickets abertos (canal de ticket já criado)
# ---------------------------------------------------------------------------

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
