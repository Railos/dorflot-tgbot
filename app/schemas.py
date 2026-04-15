from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TemplateField(BaseModel):
    name: str
    label: str
    type: Literal["string", "date", "int", "float", "image", "items", "payment_method"]
    required: bool = True
    aliases: list[str] = []


class TemplateSchema(BaseModel):
    code: str
    name: str
    fields: list[TemplateField]


def parse_field_value(field_type: str, raw_value: str):
    if field_type == "string":
        return raw_value.strip()
    if field_type == "int":
        return int(raw_value)
    if field_type == "float":
        return float(raw_value.replace(",", "."))
    if field_type == "date":
        return datetime.strptime(raw_value.strip(), "%d.%m.%Y").strftime("%d.%m.%Y")
    return raw_value
