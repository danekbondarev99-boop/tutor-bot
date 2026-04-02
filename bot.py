import asyncio
import logging
import sqlite3
import os
from datetime import datetime, timedelta, date

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from aiogram.filters import Command

# ---------------- CONFIG ----------------
API_TOKEN = os.getenv("API_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ---------------- DB ----------------
conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    role TEXT DEFAULT 'student'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    datetime TEXT
)
""")

conn.commit()

# ---------------- ADMINS ----------------
ADMIN_IDS = set()

def is_admin(user_id: int):
    cursor.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return user_id in ADMIN_IDS or (row and row[0] == "admin")

# ---------------- NAVIGATION ----------------
def back_btn():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def main_menu(user_id: int):
    if is_admin(user_id):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить занятие", callback_data="add_lesson")],
            [InlineKeyboardButton(text="📅 Все занятия", callback_data="all_lessons")],
            [InlineKeyboardButton(text="👨‍🎓 Ученики", callback_data="students")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Мои занятия", callback_data="my_lessons")]
        ])

# ---------------- TIME / DATE ----------------
def date_kb():
    today = date.today()

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(today), callback_data=f"date_{today}")],
        [InlineKeyboardButton(text=str(today + timedelta(days=1)), callback_data=f"date_{today + timedelta(days=1)}")],
        [InlineKeyboardButton(text=str(today + timedelta(days=2)), callback_data=f"date_{today + timedelta(days=2)}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def time_kb():
    times = [f"{h:02d}:00" for h in range(8, 22)]

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=f"time_{t}")]
        for t in times
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]])

# ---------------- TEMP STATE ----------------
temp = {}

# ---------------- START ----------------
@dp.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
        (user_id, message.from_user.first_name)
    )
    conn.commit()

    await message.answer(
        "📊 CRM система\nВыберите действие:",
        reply_markup=main_menu(user_id)
    )

# ---------------- BACK ----------------
@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery):
    await call.message.answer(
        "📊 Главное меню",
        reply_markup=main_menu(call.from_user.id)
    )

# ---------------- STUDENT VIEW ----------------
@dp.callback_query(F.data == "my_lessons")
async def my_lessons(call: CallbackQuery):
    user_id = call.from_user.id

    cursor.execute("SELECT datetime FROM lessons WHERE student_id=?", (user_id,))
    lessons = cursor.fetchall()

    if not lessons:
        await call.message.answer("📭 Нет занятий", reply_markup=back_btn())
        return

    text = "📅 Твои занятия:\n\n"
    for l in lessons:
        text += f"• {l[0]}\n"

    await call.message.answer(text, reply_markup=back_btn())

# ---------------- ADMIN: ALL LESSONS ----------------
@dp.callback_query(F.data == "all_lessons")
async def all_lessons(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    cursor.execute("""
        SELECT users.name, lessons.datetime
        FROM lessons
        LEFT JOIN users ON users.user_id = lessons.student_id
        ORDER BY lessons.datetime
    """)

    data = cursor.fetchall()

    if not data:
        await call.message.answer("📭 Нет занятий", reply_markup=back_btn())
        return

    text = "📅 Все занятия:\n\n"
    for name, dt in data:
        text += f"👤 {name} — {dt}\n"

    await call.message.answer(text, reply_markup=back_btn())

# ---------------- ADMIN: ADD LESSON ----------------
@dp.callback_query(F.data == "add_lesson")
async def add_lesson(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    cursor.execute("SELECT user_id, name FROM users WHERE role='student'")
    students = cursor.fetchall()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"student_{uid}")]
        for uid, name in students
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]])

    await call.message.answer("👨‍🎓 Выбери ученика:", reply_markup=kb)

@dp.callback_query(F.data.startswith("student_"))
async def pick_student(call: CallbackQuery):
    student_id = int(call.data.split("_")[1])
    temp[call.from_user.id] = {"student_id": student_id}

    await call.message.answer("📅 Выбери дату:", reply_markup=date_kb())

@dp.callback_query(F.data.startswith("date_"))
async def pick_date(call: CallbackQuery):
    d = call.data.replace("date_", "")
    temp[call.from_user.id]["date"] = d

    await call.message.answer("⏰ Выбери время:", reply_markup=time_kb())

@dp.callback_query(F.data.startswith("time_"))
async def pick_time(call: CallbackQuery):
    t = call.data.replace("time_", "")
    data = temp.get(call.from_user.id)

    if not data:
        await call.message.answer("Ошибка", reply_markup=back_btn())
        return

    dt = f"{data['date']} {t}"

    cursor.execute(
        "INSERT INTO lessons (student_id, datetime) VALUES (?, ?)",
        (data["student_id"], dt)
    )
    conn.commit()

    await call.message.answer(
        f"✅ Занятие создано:\n{dt}",
        reply_markup=back_btn()
    )

# ---------------- STUDENTS LIST ----------------
@dp.callback_query(F.data == "students")
async def students(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    cursor.execute("SELECT name, user_id, role FROM users")
    data = cursor.fetchall()

    text = "👨‍🎓 Пользователи:\n\n"
    for name, uid, role in data:
        text += f"{name} | {role} | {uid}\n"

    await call.message.answer(text, reply_markup=back_btn())

# ---------------- REMINDERS ----------------
async def reminder_loop():
    while True:
        now = datetime.now()

        cursor.execute("SELECT student_id, datetime FROM lessons")
        lessons = cursor.fetchall()

        for student_id, dt in lessons:
            try:
                lesson_time = datetime.strptime(dt, "%Y-%m-%d %H:%M")

                # 2 часа до
                if lesson_time - timedelta(hours=2) <= now < lesson_time - timedelta(hours=1, minutes=59):
                    await bot.send_message(student_id, "⏰ Через 2 часа занятие")

                # пропуск
                if now > lesson_time + timedelta(minutes=15):
                    await bot.send_message(student_id, "❌ Ты пропустил занятие")

            except:
                pass

        await asyncio.sleep(60)

# ---------------- MAIN ----------------
async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
