from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def templates_keyboard(templates):
    buttons = [
        [InlineKeyboardButton(text=template.name, callback_data=f"tpl:{template.code}")]
        for template in templates
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def result_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Создать еще документ", callback_data="create_again")]
        ]
    )

def sellers_keyboard(sellers):
    buttons = [
        [InlineKeyboardButton(text=seller.label, callback_data=f"seller:{seller.id}")]
        for seller in sellers
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_method_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Наличные", callback_data="payment:cash")],
            [InlineKeyboardButton(text="Расчетный счет", callback_data="payment:account")],
            [InlineKeyboardButton(text="QR", callback_data="payment:qr")],
        ]
    )


def input_mode_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Заполнить вручную", callback_data="input:manual")],
            [InlineKeyboardButton(text="Отправить текст", callback_data="input:text")],
        ]
    )


def buyer_type_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Физлицо", callback_data="buyer:individual")],
            [InlineKeyboardButton(text="Юрлицо", callback_data="buyer:legal")],
        ]
    )
