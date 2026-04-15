# Reply клавиатуры (постоянные кнопки внизу экрана)

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Главная Reply-клавиатура для пользователей.
    Кнопки: Расписание, Кабинет, Поддержка, Тарифы, Попробовать GregoChat
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Расписание"),
                KeyboardButton(text="Кабинет"),
            ],
            [
                KeyboardButton(text="Поддержка"),
                KeyboardButton(text="Тарифы"),
            ],
            [
                KeyboardButton(text="Попробовать GregoChat"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
    return keyboard
