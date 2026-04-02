import asyncio
import logging
import sqlite3
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ⚠️ ВАЖНО: токен больше НЕ хранится в коде
# Используй переменную окружения API_TOKEN
API_TOKEN = os.getenv("API_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ---------------- DATABASE ----------------
conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    user_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT,
    student_id INTEGER,
    datetime TEXT,
    repeat_weekly INTEGER DEFAULT 0
)
""")

conn.commit()

# ---------------- UI ----------------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить занятие")],
        [KeyboardButton(text="📋 Ученики"), KeyboardButton(text="📅 Занятия")]
    ],
    resize_keyboard=True
)

user_state = {}

# ---------------- START ----------------
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Привет! Напиши своё имя для регистрации 👇", reply_markup=main_kb)

# ---------------- REGISTER ----------------
@dp.message(F.text)
async def register_or_handle(message: Message):
    user_id = message.from_user.id
    text = message.text

    # регистрация
    cursor.execute("SELECT * FROM students WHERE user_id=?", (user_id,))
    if not cursor.fetchone() and text not in ["➕ Добавить занятие", "📋 Ученики", "📅 Занятия"]:
        cursor.execute("INSERT OR IGNORE INTO students (name, user_id) VALUES (?, ?)", (text, user_id))
        conn.commit()
        await message.answer(f"Ты зарегистрирован как {text} ✅")
        return

    # список учеников
    if text == "📋 Ученики":
        cursor.execute("SELECT name FROM students")
        data = cursor.fetchall()
        await message.answer("Ученики:\n" + "\n".join([i[0] for i in data]) if data else "Нет учеников")
        return

    # список занятий
    if text == "📅 Занятия":
        cursor.execute("SELECT id, student_name, datetime FROM lessons")
        data = cursor.fetchall()

        if not data:
            await message.answer("Нет занятий")
            return

        for i in data:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_{i[0]}")]
            ])
            await message.answer(f"{i[1]} | {i[2]}", reply_markup=kb)
        return

    # добавление занятия
    if text == "➕ Добавить занятие":
        cursor.execute("SELECT name FROM students")
        students = cursor.fetchall()

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s[0], callback_data=f"student_{s[0]}")] for s in students
        ])

        await message.answer("Выбери ученика 👇", reply_markup=kb)
        return

    # ввод даты
    if user_id in user_state:
        try:
            lesson_time = datetime.strptime(text, "%Y-%m-%d %H:%M")
            student_name = user_state[user_id]

            cursor.execute("SELECT user_id FROM students WHERE name=?", (student_name,))
            student = cursor.fetchone()

            if not student:
                await message.answer("Ошибка: ученик не найден")
                return

            student_id = student[0]

            cursor.execute(
                "INSERT INTO lessons (student_name, student_id, datetime) VALUES (?, ?, ?)",
                (student_name, student_id, lesson_time.isoformat())
            )
            conn.commit()

            schedule_reminders(student_name, student_id, lesson_time)

            await message.answer("Занятие добавлено ✅")
            del user_state[user_id]

        except Exception:
            await message.answer("Формат: YYYY-MM-DD HH:MM")

# ---------------- CALLBACKS ----------------
@dp.callback_query(F.data.startswith("student_"))
async def choose_student(call: CallbackQuery):
    name = call.data.split("_")[1]
    user_state[call.from_user.id] = name
    await call.message.answer("Введи дату и время (YYYY-MM-DD HH:MM)")

@dp.callback_query(F.data.startswith("del_"))
async def delete(call: CallbackQuery):
    lesson_id = call.data.split("_")[1]
    cursor.execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
    conn.commit()
    await call.message.edit_text("Удалено ❌")

# ---------------- REMINDERS ----------------
def schedule_reminders(name, student_id, lesson_time):
    scheduler.add_job(send_24h, "date", run_date=lesson_time - timedelta(hours=24), args=[name, student_id, lesson_time])
    scheduler.add_job(send_2h, "date", run_date=lesson_time - timedelta(hours=2), args=[name, student_id, lesson_time])

async def send_24h(name, student_id, lesson_time):
    await bot.send_message(student_id, f"📅 Завтра занятие в {lesson_time.strftime('%H:%M')}")

async def send_2h(name, student_id, lesson_time):
    await bot.send_message(student_id, f"⏰ Через 2 часа занятие в {lesson_time.strftime('%H:%M')}")

# ---------------- MAIN ----------------
async def main():
    if not API_TOKEN:
        print("❌ Нет API_TOKEN в переменных окружения")
        return

    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

# ⚠️ ВАЖНО
# Ты случайно слил токен бота. Обязательно зайди в @BotFather и сделай /revoke, затем создай новый.
# Иначе бот могут украсть.
