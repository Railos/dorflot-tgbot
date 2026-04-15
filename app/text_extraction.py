import json
import logging

from openai import OpenAI

from app.config import settings


def extract_fields_from_text(text: str, fields: list[dict]) -> dict:
    client = OpenAI(api_key=settings.openai_api_key)
    schema_fields = []
    for field in fields:
        if field.get("type") in {"image", "items"}:
            continue
        schema_fields.append(
            {
                "name": field.get("name"),
                "label": field.get("label"),
                "type": field.get("type"),
                "required": field.get("required", True),
                "aliases": field.get("aliases", []),
            }
        )

    system_prompt = (
        "You extract structured fields from a free-form user text. "
        "Return a JSON object with keys matching the schema field names. "
        "Do not include keys that are missing or unknown. "
        "Use the user text only; do not guess values."
    )

    user_payload = {
        "schema_fields": schema_fields,
        "text": text,
    }

    response = client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        temperature=0,
    )

    content = response.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logging.warning("OpenAI returned invalid JSON for extraction.")
        return {}

    if not isinstance(data, dict):
        return {}

    # Filter to known fields only
    allowed = {field.get("name") for field in schema_fields}
    return {k: v for k, v in data.items() if k in allowed and v not in (None, "")}
