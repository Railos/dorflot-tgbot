import json
import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.config import settings


class SellerProfile(BaseModel):
    id: str
    label: str
    fields: dict[str, str]


def load_sellers() -> list[SellerProfile]:
    path = Path(settings.sellers_path)
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("sellers", []) if isinstance(raw, dict) else raw
        return [SellerProfile.model_validate(item) for item in items]
    except (json.JSONDecodeError, ValidationError) as exc:
        logging.warning("Failed to load sellers from %s: %s", path, exc)
        return []


def get_seller_by_id(sellers: list[SellerProfile], seller_id: str) -> SellerProfile | None:
    for seller in sellers:
        if seller.id == seller_id:
            return seller
    return None
