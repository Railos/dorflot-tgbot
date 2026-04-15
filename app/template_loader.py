import json
from pathlib import Path

from app.config import settings
from app.schemas import TemplateSchema


def get_template_dirs() -> list[Path]:
    root = Path(settings.templates_dir)
    if not root.exists():
        return []
    return [item for item in root.iterdir() if item.is_dir()]


def load_all_templates() -> list[TemplateSchema]:
    allowed = {"buysell", "transport"}
    templates = []
    for template_dir in get_template_dirs():
        if template_dir.name not in allowed:
            continue
        schema_path = template_dir / "schema.json"
        if not schema_path.exists():
            continue

        with open(schema_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        templates.append(TemplateSchema.model_validate(raw))
    return templates


def get_template_by_code(code: str) -> tuple[TemplateSchema, str]:
    template_dir = Path(settings.templates_dir) / code
    schema_path = template_dir / "schema.json"
    template_path = template_dir / "template.docx"
    template_individual = template_dir / "template_individual.docx"
    template_legal = template_dir / "template_legal.docx"

    if not schema_path.exists():
        raise FileNotFoundError(f"Не найден schema.json для шаблона {code}")

    if not template_path.exists() and not template_individual.exists() and not template_legal.exists():
        raise FileNotFoundError(f"?? ?????? template.docx ??? ??????? {code}")

    with open(schema_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    schema = TemplateSchema.model_validate(raw)
    return schema, str(template_path)
