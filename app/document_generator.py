import logging
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2 import TemplateSyntaxError

from app.config import settings
from app.utils import generate_document_filename


def prepare_context(context: dict, doc: DocxTemplate, *, include_images: bool) -> dict:
    prepared = {}
    for key, value in context.items():
        if isinstance(value, dict) and value.get("_type") == "image":
            if include_images:
                image_path = value.get("path")
                width_mm = value.get("width_mm", 40)
                prepared[key] = InlineImage(doc, image_path, width=Mm(width_mm))
            else:
                prepared[key] = ""
        else:
            prepared[key] = value
    return prepared


def render_docx_to_path(template_path: str, context: dict, *, output_path: str, include_images: bool) -> str:
    doc = DocxTemplate(template_path)
    doc.render(prepare_context(context, doc, include_images=include_images))
    doc.save(output_path)
    if include_images:
        _remove_underline_from_image_runs(output_path)

    return output_path


def _remove_underline_from_image_runs(docx_path: str) -> None:
    """
    Word can render an underline/line under an InlineImage if the placeholder run (or its paragraph style)
    had underline formatting applied. This post-process removes underline formatting from runs that contain
    drawings so signature/stamp images don't have a line drawn through/under them.
    """

    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    }

    def strip_underline(xml_bytes: bytes) -> bytes:
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return xml_bytes

        changed = False
        for run in root.findall(".//w:r", namespaces):
            if run.find(".//w:drawing", namespaces) is None:
                continue
            rpr = run.find("w:rPr", namespaces)
            if rpr is None:
                continue
            underline = rpr.find("w:u", namespaces)
            if underline is not None:
                rpr.remove(underline)
                changed = True

        if not changed:
            return xml_bytes
        return ET.tostring(root, encoding="utf-8", xml_declaration=False)

    # Patch common Word XML parts where images might exist.
    target_names: list[str] = ["word/document.xml"]
    try:
        import zipfile

        with zipfile.ZipFile(docx_path, "r") as zin:
            names = zin.namelist()
            for name in names:
                if name.startswith("word/header") and name.endswith(".xml"):
                    target_names.append(name)
                if name.startswith("word/footer") and name.endswith(".xml"):
                    target_names.append(name)

            updated: dict[str, bytes] = {}
            for name in target_names:
                if name in names:
                    updated[name] = strip_underline(zin.read(name))

            if not updated:
                return

            entries = {name: zin.read(name) for name in names if name not in updated}
            entries.update(updated)

        with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name, data in entries.items():
                zout.writestr(name, data)
    except OSError:
        logging.exception("Failed to post-process DOCX for image underline cleanup: %s", docx_path)


def _find_libreoffice_executable() -> str | None:
    if settings.libreoffice_path:
        candidate = Path(settings.libreoffice_path)
        if candidate.is_dir():
            for name in ("soffice.exe", "soffice", "libreoffice.exe", "libreoffice"):
                exe = candidate / name
                if exe.is_file():
                    return str(exe)
        if candidate.is_file():
            return str(candidate)

    for name in ("libreoffice", "soffice", "libreoffice.exe", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found

    if os.name == "nt":
        common_locations = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "LibreOffice"
            / "program"
            / "soffice.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "LibreOffice"
            / "program"
            / "soffice.exe",
        ]
        for path in common_locations:
            if path.exists():
                return str(path)

    return None


def convert_to_pdf(docx_path: str) -> str | None:
    if not settings.pdf_enabled:
        return None

    output_dir = settings.generated_dir
    libreoffice = _find_libreoffice_executable()
    if not libreoffice:
        logging.warning(
            "PDF conversion skipped: LibreOffice not found (set LIBREOFFICE_PATH or add soffice to PATH)."
        )
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
        logging.info("Converting to PDF via LibreOffice: %s", command[0])
        subprocess.run(command, check=True)
    except FileNotFoundError:
        logging.warning("PDF conversion skipped: libreoffice executable not found.")
        return None
    except PermissionError:
        logging.exception(
            "PDF conversion failed: permission denied when launching LibreOffice (%s).",
            command[0],
        )
        return None

    pdf_name = Path(docx_path).with_suffix(".pdf").name
    pdf_path = str(Path(output_dir) / pdf_name)
    if not Path(pdf_path).exists():
        logging.warning("PDF conversion finished, but output PDF not found at: %s", pdf_path)
        return None
    return pdf_path


def generate_document(
    template_path: str,
    context: dict,
    need_pdf: bool = True,
    document_type: str | None = None,
    seller_name: str | None = None,
) -> dict:
    try:
        docx_path = generate_document_filename(
            document_type=document_type,
            seller_name=seller_name,
            extension="docx",
            output_dir=settings.generated_dir,
        )

        render_docx_to_path(
            template_path,
            context,
            output_path=docx_path,
            include_images=False,
        )
    except TemplateSyntaxError as exc:
        raise TemplateSyntaxError(
            f"Template error in {template_path}: {exc.message}",
            exc.lineno,
            exc.name,
            exc.filename,
        ) from exc

    pdf_path = None
    if need_pdf:
        # Render a separate DOCX that includes images (signature/stamp) and convert it to PDF,
        # while keeping the user-facing DOCX clean (no images).
        pdf_source_dir = Path(settings.temp_dir) / f"pdfsrc_{Path(docx_path).stem}"
        pdf_source_dir.mkdir(parents=True, exist_ok=True)
        pdf_source_docx_path = str(pdf_source_dir / Path(docx_path).name)
        try:
            render_docx_to_path(
                template_path,
                context,
                output_path=pdf_source_docx_path,
                include_images=True,
            )
            pdf_path = convert_to_pdf(pdf_source_docx_path)
        except TemplateSyntaxError as exc:
            raise TemplateSyntaxError(
                f"Template error in {template_path}: {exc.message}",
                exc.lineno,
                exc.name,
                exc.filename,
            ) from exc
        finally:
            try:
                shutil.rmtree(pdf_source_dir, ignore_errors=True)
            except Exception:
                logging.exception("Failed to clean up PDF source directory: %s", pdf_source_dir)

    return {
        "docx_path": docx_path,
        "pdf_path": pdf_path,
    }
