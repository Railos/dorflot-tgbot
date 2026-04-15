import logging
import shutil
import subprocess
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2 import TemplateSyntaxError

from app.config import settings
from app.utils import generate_document_filename


def prepare_context(context: dict, doc: DocxTemplate) -> dict:
    prepared = {}
    for key, value in context.items():
        if isinstance(value, dict) and value.get("_type") == "image":
            image_path = value.get("path")
            width_mm = value.get("width_mm", 40)
            prepared[key] = InlineImage(doc, image_path, width=Mm(width_mm))
        else:
            prepared[key] = value
    return prepared


def render_docx(template_path: str, context: dict, document_type: str | None, seller_name: str | None) -> str:
    output_path = generate_document_filename(
        document_type=document_type,
        seller_name=seller_name,
        extension="docx",
        output_dir=settings.generated_dir,
    )

    doc = DocxTemplate(template_path)
    doc.render(prepare_context(context, doc))
    doc.save(output_path)

    return output_path


def convert_to_pdf(docx_path: str) -> str | None:
    if not settings.pdf_enabled:
        return None

    output_dir = settings.generated_dir
    libreoffice = shutil.which("libreoffice")
    if not libreoffice:
        logging.warning("PDF conversion skipped: libreoffice not found in PATH.")
        return None

    command = [
        libreoffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        output_dir,
        docx_path,
    ]

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        logging.warning("PDF conversion skipped: libreoffice executable not found.")
        return None

    pdf_path = str(Path(docx_path).with_suffix(".pdf"))
    return pdf_path


def generate_document(
    template_path: str,
    context: dict,
    need_pdf: bool = True,
    document_type: str | None = None,
    seller_name: str | None = None,
) -> dict:
    try:
        docx_path = render_docx(template_path, context, document_type, seller_name)
    except TemplateSyntaxError as exc:
        raise TemplateSyntaxError(
            f"Template error in {template_path}: {exc.message}",
            exc.lineno,
            exc.name,
            exc.filename,
        ) from exc
    pdf_path = convert_to_pdf(docx_path) if need_pdf else None

    return {
        "docx_path": docx_path,
        "pdf_path": pdf_path,
    }
