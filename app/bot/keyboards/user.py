from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
)

TRIAL_BUTTON_TEXT = "🎁 Пробный период"
SUBSCRIPTION_BUTTON_TEXT = "📋 Моя подписка"


def get_user_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт постоянную клавиатуру клиента."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=TRIAL_BUTTON_TEXT),
                KeyboardButton(text=SUBSCRIPTION_BUTTON_TEXT),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие",
    )