import json
import threading
from pathlib import Path

from app.config import settings

_lock = threading.Lock()


def _load() -> dict:
    path = Path(settings.counters_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def allocate_next_transport_number(user_id: int) -> int:
    with _lock:
        data = _load()
        transport = data.get("transport", {})
        current = int(transport.get(str(user_id), 0) or 0)
        return current + 1


def commit_transport_number(user_id: int, number: int) -> None:
    with _lock:
        path = Path(settings.counters_path)
        data = _load()
        transport = data.get("transport", {})
        current = int(transport.get(str(user_id), 0) or 0)
        if number > current:
            transport[str(user_id)] = number
            data["transport"] = transport
            _atomic_write_json(path, data)
