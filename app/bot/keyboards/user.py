from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models.plan import Plan

BUY_BUTTON_TEXT = "🛒 Выбрать тариф"
SUBSCRIPTION_BUTTON_TEXT = "📋 Моя подписка"
TRIAL_BUTTON_TEXT = "🎁 Пробный период"


def get_user_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт постоянную клавиатуру клиента."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=SUBSCRIPTION_BUTTON_TEXT),
            ],
            [
                KeyboardButton(text=TRIAL_BUTTON_TEXT),
                KeyboardButton(text=BUY_BUTTON_TEXT),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие",
    )


def get_buy_keyboard(plans: list[Plan]) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для выбора тарифа."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{plan.name} — {plan.price_rub} ₽",
                    callback_data=f"buy:{plan.id}",
                )
            ]
            for plan in plans
        ]
    )