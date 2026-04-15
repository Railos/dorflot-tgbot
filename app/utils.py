from pathlib import Path
from uuid import uuid4


def ensure_dirs(*dirs: str) -> None:
    for directory in dirs:
        Path(directory).mkdir(parents=True, exist_ok=True)


def generate_output_filename(extension: str) -> str:
    return f"{uuid4().hex}.{extension}"


def sanitize_filename_part(value: str) -> str:
    cleaned = []
    for char in value.strip():
        if char.isalnum() or char in {"_", "-", " "}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    result = "".join(cleaned).strip().replace(" ", "_")
    while "__" in result:
        result = result.replace("__", "_")
    return result.strip("_")


def generate_document_filename(
    document_type: str | None,
    seller_name: str | None,
    extension: str,
    output_dir: str,
) -> str:
    doc_part = sanitize_filename_part(document_type or "document")
    seller_part = sanitize_filename_part(seller_name or "seller")
    base = f"{doc_part}_{seller_part}"

    output_path = Path(output_dir) / f"{base}.{extension}"
    if not output_path.exists():
        return str(output_path)

    index = 2
    while True:
        candidate = Path(output_dir) / f"{base}_{index}.{extension}"
        if not candidate.exists():
            return str(candidate)
        index += 1
