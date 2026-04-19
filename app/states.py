from aiogram.fsm.state import State, StatesGroup


class FillDocumentState(StatesGroup):
    configuring = State()
    selecting_seller = State()
    selecting_input_mode = State()
    selecting_buyer_type = State()
    selecting_output_format = State()
    collecting_text = State()
    selecting_payment_method = State()
    filling = State()
