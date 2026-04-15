import asyncio
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from app.config import settings
from app.document_generator import generate_document
from app.keyboards import (
    buyer_type_keyboard,
    input_mode_keyboard,
    payment_method_keyboard,
    result_keyboard,
    sellers_keyboard,
    templates_keyboard,
)
from app.schemas import parse_field_value
from app.sellers import get_seller_by_id, load_sellers
from app.text_extraction import extract_fields_from_text
from app.states import FillDocumentState
from app.template_loader import get_template_by_code, load_all_templates
from app.utils import generate_output_filename

router = Router()


async def save_image_from_message(message: Message) -> str | None:
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type:
        if message.document.mime_type.startswith("image/"):
            file_id = message.document.file_id

    if not file_id:
        return None

    file_info = await message.bot.get_file(file_id)
    suffix = Path(file_info.file_path).suffix.lstrip(".") or "jpg"
    output_path = Path(settings.temp_dir) / generate_output_filename(suffix)

    await message.bot.download_file(file_info.file_path, destination=output_path)
    asyncio.create_task(delete_files_later([str(output_path)], delay_seconds=600))
    return str(output_path)


def get_seller_field_names(fields: list[dict], sellers) -> set[str]:
    seller_keys = set()
    for seller in sellers:
        seller_keys.update(seller.fields.keys())
    return {field["name"] for field in fields if field["name"] in seller_keys}


def apply_seller_to_fields(fields: list[dict], seller) -> tuple[list[dict], dict]:
    remaining = []
    answers = {}
    for field in fields:
        name = field["name"]
        value = seller.fields.get(name)
        if value is None or value == "":
            remaining.append(field)
        else:
            answers[name] = normalize_seller_value(name, value)
    return remaining, answers


def normalize_seller_value(name: str, value):
    if name == "seller_signature":
        return {"_type": "image", "path": value, "width_mm": 20}
    if name == "seller_stamp":
        return {"_type": "image", "path": value, "width_mm": 50}
    return value


BUYER_INDIVIDUAL_FIELDS = {
    "full_name",
    "initials",
    "address",
    "passport_seriya",
    "passport_nomer",
    "passport_kem",
    "passport_kogda",
    "passport_kod",
    "signature_pok",
}

BUYER_LEGAL_FIELDS = {
    "buyer_company_name",
    "buyer_inn",
    "buyer_ogrn",
    "buyer_bik",
    "buyer_schet",
    "buyer_bank",
    "buyer_director_name",
    "signature_pok",
}
BUYER_ALL_FIELDS = BUYER_INDIVIDUAL_FIELDS | BUYER_LEGAL_FIELDS


def apply_buyer_type_filter(fields: list[dict], buyer_type: str) -> list[dict]:
    if buyer_type == "individual":
        allowed = BUYER_INDIVIDUAL_FIELDS
    elif buyer_type == "legal":
        allowed = BUYER_LEGAL_FIELDS
    else:
        return fields

    filtered = []
    for field in fields:
        name = field["name"]
        if name not in BUYER_ALL_FIELDS or name in allowed:
            filtered.append(field)
    return filtered


def filter_filled_fields(fields: list[dict], answers: dict) -> list[dict]:
    remaining = []
    for field in fields:
        name = field["name"]
        value = answers.get(name)
        if value is None or value == "":
            remaining.append(field)
    return remaining


def compute_initials(full_name: str) -> str | None:
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        return None
    surname = parts[0]
    initials = []
    if len(parts) >= 2:
        initials.append(f"{parts[1][0]}.")
    if len(parts) >= 3:
        initials.append(f"{parts[2][0]}.")
    if initials:
        return f"{surname} {' '.join(initials)}"
    return surname


def prepare_fields_for_initials(fields: list[dict], answers: dict) -> list[dict]:
    full_name = answers.get("full_name")
    if full_name and not answers.get("initials"):
        computed = compute_initials(full_name)
        if computed:
            answers["initials"] = computed
    return filter_filled_fields(fields, answers)


async def proceed_to_input_mode(message: Message, state: FSMContext) -> None:
    await state.set_state(FillDocumentState.selecting_input_mode)
    await message.answer(
        "Как заполняем документ?",
        reply_markup=input_mode_keyboard(),
    )


async def proceed_to_buyer_type(message: Message, state: FSMContext, fields: list[dict], answers: dict) -> None:
    await state.set_state(FillDocumentState.selecting_buyer_type)
    await state.update_data(fields=fields, answers=answers, current_index=0)
    await message.answer(
        "Выберите тип покупателя:",
        reply_markup=buyer_type_keyboard(),
    )


async def proceed_to_filling(message: Message, state: FSMContext, fields: list[dict], answers: dict) -> None:
    remaining_fields = prepare_fields_for_initials(fields, answers)
    await state.set_state(FillDocumentState.filling)
    await state.update_data(
        fields=remaining_fields,
        current_index=0,
        answers=answers,
    )

    if not remaining_fields:
        template_queue = (await state.get_data()).get("template_queue", [])
        await send_generated_documents_batch(message, template_queue, answers)
        await state.clear()
        return

    first_field = remaining_fields[0]
    if first_field["type"] == "payment_method":
        await message.answer("Выберите способ оплаты:", reply_markup=payment_method_keyboard())
    else:
        await message.answer(first_field["label"])


def to_number(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


async def send_generated_documents_batch(message: Message, template_queue: list[str], answers: dict) -> None:
    await message.answer("Документы готовятся...")
    cleanup_paths: list[str] = []
    for code in template_queue:
        _, template_path = get_template_by_code(code)
        buyer_type = answers.get("buyer_type")
        template_path = select_buyer_template_path(code, template_path, buyer_type)
        generated = generate_document(
            template_path,
            answers,
            need_pdf=True,
            document_type=code,
            seller_name=answers.get("seller_name"),
        )
        cleanup_paths.append(generated["docx_path"])

        docx_file = FSInputFile(generated["docx_path"])
        await message.answer_document(docx_file, caption="Готовый DOCX")

        if generated["pdf_path"]:
            cleanup_paths.append(generated["pdf_path"])
            pdf_file = FSInputFile(generated["pdf_path"])
            await message.answer_document(
                pdf_file,
                caption="Готовый PDF",
            )

    await message.answer("Документы готовы.", reply_markup=result_keyboard())
    asyncio.create_task(delete_files_later(cleanup_paths, delay_seconds=600))


async def prompt_items_count(message: Message, state: FSMContext) -> None:
    await message.answer("Сколько позиций?")
    await state.update_data(items_state={"step": "count"})


async def handle_items_flow(message: Message, state: FSMContext, data: dict) -> bool:
    items_state = data.get("items_state")
    if not items_state:
        return False

    step = items_state.get("step")
    if step == "count":
        try:
            total = int(message.text.strip())
        except (TypeError, ValueError):
            await message.answer("Введите число позиций.")
            return True
        if total <= 0:
            await message.answer("Количество должно быть больше нуля.")
            return True

        items_state = {
            "step": "articul",
            "total": total,
            "index": 0,
            "items": [],
            "current": {},
        }
        await state.update_data(items_state=items_state)
        await message.answer("Позиция 1: артикул")
        return True

    total = items_state["total"]
    index = items_state["index"]
    current = items_state["current"]

    if step == "articul":
        current["articul"] = message.text.strip()
        items_state["step"] = "name"
        await state.update_data(items_state=items_state)
        await message.answer(f"Позиция {index + 1}: наименование")
        return True

    if step == "name":
        current["name"] = message.text.strip()
        items_state["step"] = "price"
        await state.update_data(items_state=items_state)
        await message.answer(f"Позиция {index + 1}: цена")
        return True

    if step == "price":
        try:
            price = parse_field_value("float", message.text)
        except Exception:
            await message.answer("Некорректная цена. Введите число.")
            return True

        current["price"] = price
        items_state["items"].append(
            {
                "n": index + 1,
                "articul": current["articul"],
                "name": current["name"],
                "price": current["price"],
            }
        )

        index += 1
        if index >= total:
            answers = data["answers"]
            answers["items"] = items_state["items"]
            answers["itog_sum"] = sum(item["price"] for item in items_state["items"])
            current_index = data["current_index"] + 1
            fields = data["fields"]
            template_queue = data.get("template_queue", [])

            await state.update_data(
                answers=answers,
                current_index=current_index,
                items_state=None,
            )

            if current_index >= len(fields):
                await send_generated_documents_batch(message, template_queue, answers)
                await state.clear()
                return True

            next_field = fields[current_index]
            if next_field["type"] == "items":
                await prompt_items_count(message, state)
                return True
            if next_field["type"] == "payment_method":
                await message.answer("Выберите способ оплаты:", reply_markup=payment_method_keyboard())
                return True

            await message.answer(next_field["label"])
            return True

        items_state["index"] = index
        items_state["current"] = {}
        items_state["step"] = "articul"
        await state.update_data(items_state=items_state)
        await message.answer(f"Позиция {index + 1}: артикул")
        return True

    return False


def select_buyer_template_path(code: str, default_path: str, buyer_type: str | None) -> str:
    if buyer_type not in {"individual", "legal"}:
        return default_path
    candidate = Path(settings.templates_dir) / code / f"template_{buyer_type}.docx"
    if candidate.exists():
        return str(candidate)
    return default_path


async def delete_files_later(paths: list[str], delay_seconds: int) -> None:
    await asyncio.sleep(delay_seconds)
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


@router.message(CommandStart())
async def start_handler(message: Message):
    templates = load_all_templates()
    if not templates:
        await message.answer("Шаблоны пока не загружены.")
        return

    await message.answer(
        "Выберите шаблон документа:",
        reply_markup=templates_keyboard(templates),
    )


@router.callback_query(F.data.startswith("tpl:"))
async def select_template(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    template_queue = ["transport", "transport_pril1", "transport_pril2"] if code == "transport" else [code]

    fields = []
    seen = set()
    for template_code in template_queue:
        schema, _ = get_template_by_code(template_code)
        for field in schema.fields:
            if field.name in seen:
                continue
            seen.add(field.name)
            fields.append(field.model_dump())

    await state.update_data(
        template_queue=template_queue,
        fields=fields,
        current_index=0,
        answers={},
        seller_selected=False,
    )

    sellers = load_sellers()
    seller_fields = get_seller_field_names(fields, sellers)
    if sellers and seller_fields:
        await state.set_state(FillDocumentState.selecting_seller)
        await callback.message.answer(
            "Выберите продавца:",
            reply_markup=sellers_keyboard(sellers),
        )
        await callback.answer()
        return

    await proceed_to_buyer_type(callback.message, state, fields, {})
    await callback.answer()


@router.callback_query(F.data.startswith("seller:"))
async def select_seller(callback: CallbackQuery, state: FSMContext):
    seller_id = callback.data.split(":", 1)[1]
    sellers = load_sellers()
    seller = get_seller_by_id(sellers, seller_id)
    if not seller:
        await callback.message.answer("Продавец не найден. Выберите продавца еще раз.")
        await callback.message.answer("Выберите продавца:", reply_markup=sellers_keyboard(sellers))
        await callback.answer()
        return

    data = await state.get_data()
    fields = data.get("fields", [])
    answers = data.get("answers", {})

    remaining_fields, seller_answers = apply_seller_to_fields(fields, seller)
    answers.update(seller_answers)

    await state.update_data(
        fields=remaining_fields,
        current_index=0,
        answers=answers,
        seller_selected=True,
    )
    await proceed_to_buyer_type(callback.message, state, remaining_fields, answers)
    await callback.answer()


@router.callback_query(F.data.startswith("buyer:"))
async def select_buyer_type(callback: CallbackQuery, state: FSMContext):
    buyer_type = callback.data.split(":", 1)[1]
    data = await state.get_data()
    fields = data.get("fields", [])
    answers = data.get("answers", {})
    template_queue = data.get("template_queue", [])

    filtered_fields = apply_buyer_type_filter(fields, buyer_type)
    remaining_fields = prepare_fields_for_initials(filtered_fields, answers)
    answers["buyer_type"] = buyer_type

    await state.set_state(FillDocumentState.selecting_input_mode)
    await state.update_data(
        fields=remaining_fields,
        current_index=0,
        answers=answers,
        buyer_type=buyer_type,
    )

    await proceed_to_input_mode(callback.message, state)
    await callback.answer()


@router.callback_query(F.data.startswith("input:"))
async def select_input_mode(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    data = await state.get_data()
    fields = data.get("fields", [])
    answers = data.get("answers", {})

    if choice == "manual":
        await proceed_to_filling(callback.message, state, fields, answers)
        await callback.answer()
        return

    missing = []
    for field in fields:
        name = field.get("name")
        if not name or name in answers:
            continue
        if field.get("type") == "image":
            continue
        label = field.get("label") or name
        missing.append(f"- {name}: {label}")

    if missing:
        await callback.message.answer(
            "Поля для заполнения:\n" + "\n".join(missing)
        )

    await state.set_state(FillDocumentState.collecting_text)
    await callback.message.answer("Отправьте одним сообщением текст с данными.")
    await callback.answer()


@router.message(FillDocumentState.collecting_text)
async def collect_text(message: Message, state: FSMContext):
    data = await state.get_data()
    fields = data.get("fields", [])
    answers = data.get("answers", {})

    try:
        extracted = extract_fields_from_text(message.text, fields)
    except Exception:
        logging.exception("Text extraction failed.")
        await message.answer("Не удалось разобрать текст. Попробуйте еще раз или заполните вручную.")
        return
    answers.update(extracted)
    prepare_fields_for_initials(fields, answers)

    await state.update_data(answers=answers)
    if not extracted:
        await message.answer("Не удалось извлечь данные из текста. Продолжим вручную.")
    await proceed_to_filling(message, state, fields, answers)

@router.callback_query(F.data.startswith("payment:"))
async def select_payment_method(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    label_map = {
        "cash": "Наличные",
        "account": "Расчетный счет",
        "qr": "QR",
    }
    value = label_map.get(choice, choice)

    data = await state.get_data()
    fields = data.get("fields", [])
    current_index = data.get("current_index", 0)
    answers = data.get("answers", {})
    template_queue = data.get("template_queue", [])

    current_field = fields[current_index]
    answers[current_field["name"]] = value

    current_index += 1
    while current_index < len(fields) and fields[current_index]["name"] == "initials" and answers.get("initials"):
        current_index += 1

    if current_index >= len(fields):
        await send_generated_documents_batch(callback.message, template_queue, answers)
        await state.clear()
        await callback.answer()
        return

    await state.update_data(
        current_index=current_index,
        answers=answers,
    )

    next_field = fields[current_index]
    if next_field["type"] == "items":
        await prompt_items_count(callback.message, state)
        await callback.answer()
        return
    if next_field["type"] == "payment_method":
        await callback.message.answer("Выберите способ оплаты:", reply_markup=payment_method_keyboard())
        await callback.answer()
        return

    await callback.message.answer(next_field["label"])
    await callback.answer()


@router.callback_query(F.data == "create_again")
async def create_again(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    templates = load_all_templates()
    await callback.message.answer(
        "Выберите шаблон документа:",
        reply_markup=templates_keyboard(templates),
    )
    await callback.answer()


@router.message(FillDocumentState.filling)
async def fill_document(message: Message, state: FSMContext):
    data = await state.get_data()
    if await handle_items_flow(message, state, data):
        return

    fields = data["fields"]
    current_index = data["current_index"]
    answers = data["answers"]
    template_queue = data.get("template_queue", [])

    current_field = fields[current_index]
    field_type = current_field["type"]

    if field_type == "payment_method":
        await message.answer("Выберите способ оплаты:", reply_markup=payment_method_keyboard())
        return

    if field_type == "items":
        await prompt_items_count(message, state)
        return

    if field_type == "image":
        image_path = await save_image_from_message(message)
        if not image_path:
            await message.answer("Пожалуйста, отправьте изображение подписи (фото или файл).")
            return
        value = {"_type": "image", "path": image_path, "width_mm": 20}
    else:
        try:
            value = parse_field_value(field_type, message.text)
        except Exception:
            await message.answer(f"Некорректное значение. {current_field['label']}")
            return

    answers[current_field["name"]] = value
    if current_field["name"] == "full_name" and not answers.get("initials"):
        computed = compute_initials(str(value))
        if computed:
            answers["initials"] = computed
    if current_field["name"] == "predoplata":
        itog_sum = to_number(answers.get("itog_sum"))
        predoplata = to_number(value)
        if itog_sum is not None and predoplata is not None:
            answers["ostalnoe"] = itog_sum - predoplata

    current_index += 1
    while current_index < len(fields) and fields[current_index]["name"] == "initials" and answers.get("initials"):
        current_index += 1

    if current_index >= len(fields):
        await send_generated_documents_batch(message, template_queue, answers)
        await state.clear()
        return

    await state.update_data(
        current_index=current_index,
        answers=answers,
    )

    next_field = fields[current_index]
    if next_field["type"] == "items":
        await prompt_items_count(message, state)
        return
    if next_field["type"] == "payment_method":
        await message.answer("Выберите способ оплаты:", reply_markup=payment_method_keyboard())
        return
    await message.answer(next_field["label"])
@router.message(FillDocumentState.filling)
async def fill_document(message: Message, state: FSMContext):
    data = await state.get_data()
    if await handle_items_flow(message, state, data):
        return

    fields = data["fields"]
    current_index = data["current_index"]
    answers = data["answers"]
    template_queue = data.get("template_queue", [])

    current_field = fields[current_index]
    field_type = current_field["type"]

    if field_type == "items":
        await prompt_items_count(message, state)
        return

    if field_type == "image":
        image_path = await save_image_from_message(message)
        if not image_path:
            await message.answer("??????????, ????????? ??????????? ??????? (???? ??? ????).")
            return
        value = {"_type": "image", "path": image_path, "width_mm": 20}
    else:
        try:
            value = parse_field_value(field_type, message.text)
        except Exception:
            await message.answer(f"???????????? ????????. {current_field['label']}")
            return

    answers[current_field["name"]] = value
    if current_field["name"] == "full_name" and not answers.get("initials"):
        computed = compute_initials(str(value))
        if computed:
            answers["initials"] = computed

    current_index += 1
    while current_index < len(fields) and fields[current_index]["name"] == "initials" and answers.get("initials"):
        current_index += 1

    if current_index >= len(fields):
        await send_generated_documents_batch(message, template_queue, answers)
        await state.clear()
        return

    await state.update_data(
        current_index=current_index,
        answers=answers,
    )

    next_field = fields[current_index]
    if next_field["type"] == "items":
        await prompt_items_count(message, state)
        return
    await message.answer(next_field["label"])
