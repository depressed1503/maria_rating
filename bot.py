from asyncio import run
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from dotenv import load_dotenv
from os import environ

from src.db import *

# Инициализация
init_db()
load_dotenv()
API_TOKEN = environ.get("API_TOKEN")
bot = Bot(token=API_TOKEN)
dp = Dispatcher()


# 🔧 Вспомогательные функции
def confirm_keyboard(match_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{match_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{match_id}")
        ]
    ])


# 🔁 Обновление username
def update_username(telegram_id, username):
    if username:
        with connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE players SET username = ? WHERE telegram_id = ?", (username, telegram_id))
            conn.commit()


# 📩 /start — приветствие
@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer("Привет! Это бот клуба настольного тенниса 🏓\n"
                        "Чтобы участвовать в рейтинге, введи команду /reg")


# 🆕 /reg — регистрация
@dp.message(Command("reg"))
async def cmd_reg(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username

    if not username:
        await message.answer("❗ У тебя не установлен username в Telegram. Он обязателен для участия.")
        return

    existing = get_player_by_telegram_id(user_id)
    if existing:
        await message.answer(f"✅ Ты уже зарегистрирован как @{username}.")
        update_username(user_id, username)
        return

    register_player(user_id, username)
    await message.answer(f"Добро пожаловать, @{username}! Ты теперь участник рейтинга 🏆")


# 👤 /whoami — личная инфа
@dp.message(Command("whoami"))
async def cmd_whoami(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    update_username(user_id, username)

    player = get_player_by_telegram_id(user_id)
    if not player:
        await message.answer("Ты ещё не зарегистрирован. Используй /reg")
        return

    player_id = player[0]
    rating = player[3]
    games = get_games_played(player_id)

    await message.answer(
        f"👤 @{username}\n"
        f"🏓 Рейтинг: {rating}\n"
        f"🎮 Матчей сыграно: {games}"
    )


# 🎮 /match @user 3:1 — создать матч
@dp.message(Command("match"))
async def cmd_match(message: Message):
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Формат: /match @opponent 3:1")
        return

    author = message.from_user
    author_id = author.id
    username = author.username
    update_username(author_id, username)

    opponent_tag = args[1].lstrip("@")
    score = args[2]

    try:
        s1, s2 = map(int, score.split(":"))
    except:
        await message.answer("Счёт должен быть в формате 3:1")
        return

    player1 = get_player_by_telegram_id(author_id)
    player2 = get_player_by_username(opponent_tag)

    if not player2:
        await message.answer(f"Игрок @{opponent_tag} не найден.")
        return

    if player1[0] == player2[0]:
        await message.answer("Нельзя сыграть матч с самим собой.")
        return

    winner_id = player1[0] if s1 > s2 else player2[0]
    match_id = record_match(player1[0], player2[0], s1, s2, winner_id)

    await message.answer(f"Матч отправлен на подтверждение @{opponent_tag}.")

    await bot.send_message(
        chat_id=player2[1],
        text=(
            f"🏓 Подтверждение матча от @{username}:\n"
            f"Результат: @{username} {s1}:{s2} Вы\n"
            f"Если всё верно — нажми кнопку ниже."
        ),
        reply_markup=confirm_keyboard(match_id)
    )


@dp.callback_query(F.data.startswith("confirm:"))
async def on_confirm_match(callback: CallbackQuery):
    match_id = int(callback.data.split(":")[1])

    # Получаем матч
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT player1_id, player2_id FROM matches WHERE id = ?", (match_id,))
        match = cur.fetchone()

    if not match:
        await callback.message.edit_text("❌ Матч не найден.")
        await callback.answer("Ошибка.")
        return

    player1_id, player2_id = match
    confirmer_id = callback.from_user.id

    success = confirm_match(match_id)

    if success:
        await callback.message.edit_text("✅ Матч подтверждён! Рейтинг обновлён.")
        await callback.answer("Матч записан.")

        # Уведомим инициатора (не тот, кто подтвердил)
        author_id = player1_id if get_player_by_id(player2_id)[1] == confirmer_id else player2_id
        author = get_player_by_id(author_id)

        if author:
            await bot.send_message(
                chat_id=author[1],
                text=f"✅ Матч с @{callback.from_user.username} подтверждён и засчитан!"
            )
    else:
        await callback.message.edit_text("❌ Не удалось подтвердить матч (возможно, он уже подтверждён).")
        await callback.answer("Ошибка.")


# ❌ Отклонение матча
@dp.callback_query(F.data.startswith("reject:"))
async def on_reject_match(callback: CallbackQuery):
    match_id = int(callback.data.split(":")[1])

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT player1_id, player2_id FROM matches WHERE id = ?", (match_id,))
        match = cur.fetchone()

    if not match:
        await callback.message.edit_text("⚠️ Матч не найден или уже удалён.")
        await callback.answer("Ошибка.")
        return

    player1_id, player2_id = match
    rejector_id = callback.from_user.id

    # Удаляем матч
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM matches WHERE id = ?", (match_id,))
        conn.commit()

    await callback.message.edit_text("❌ Матч отклонён.")
    await callback.answer("Матч удалён.")

    # Уведомление автору
    player1 = get_player_by_id(player1_id)
    if player1:
        await bot.send_message(
            chat_id=player1[1],
            text=f"⚠️ Матч с @{callback.from_user.username} был отклонён и не засчитан."
        )


# 📊 /rating — список лучших игроков
@dp.message(Command("rating"))
async def cmd_rating(message: Message):
    rating = get_rating_table()
    text = "<b>🏆 Рейтинг игроков:</b>\n\n"
    for i, (username, score) in enumerate(rating, start=1):
        text += f"{i}. @{username} — {score}\n"
    await message.answer(text, parse_mode=ParseMode.HTML)


# 🚀 Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    run(main())
