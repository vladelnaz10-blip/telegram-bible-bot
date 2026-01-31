import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

# ================= НАСТРОЙКИ =================
TOKEN = "7987408393:AAHGmLA9wBs6u90GBKBSap17MyBG7hniStM"
GROUP_ID = -1001336256088  # ID твоей группы

# ID тем (топиков) → категория
TOPIC_TO_CATEGORY = {
    519: "bible",
    453: "bread",
    506: "exorcism",
    510: "dreams",
    774: "abundant"
}

CATEGORY_TO_NAME = {
    "bible": "📖 Изучение Библии",
    "bread": "🍞 Хлеб с Небес",
    "exorcism": "✝ Экзорцизм",
    "dreams": "🌙 Сны и Видения",
    "abundant": "✨ Жизнь с Избытком"
}

# ================= БАЗА ДАННЫХ =================
conn = sqlite3.connect("media.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT UNIQUE,
    media_type TEXT,
    title TEXT,
    category TEXT,
    added_at TEXT
)
""")
conn.commit()

# ================= CALLBACK DATA =================
class MediaCallback(CallbackData, prefix="m"):
    action: str  # list / play / page
    cat: str
    item_id: int = 0
    page: int = 0

# ================= БОТ =================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= СОХРАНЕНИЕ ИЗ ГРУППЫ =================
@dp.message(F.chat.id == GROUP_ID)
async def handle_group_message(message: types.Message):
    if message.message_thread_id is None:
        return

    category = TOPIC_TO_CATEGORY.get(message.message_thread_id)
    if not category:
        return

    file_id = None
    media_type = None

    # -------- Определяем заголовок --------
    title = message.caption

    if not title and message.audio:
        if message.audio.title:
            title = message.audio.title
            if message.audio.performer:
                title = f"{message.audio.performer} – {title}"
        elif message.audio.file_name:
            title = message.audio.file_name.rsplit('.', 1)[0]

    if not title:
        title = f"Проповедь от {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    title = title[:200]

    # -------- Определяем тип --------
    if message.video:
        file_id = message.video.file_id
        media_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        media_type = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        media_type = "audio"

    if not file_id:
        return

    try:
        cursor.execute(
            "INSERT INTO media (file_id, media_type, title, category, added_at) VALUES (?, ?, ?, ?, ?)",
            (file_id, media_type, title, category, datetime.now().isoformat())
        )
        conn.commit()
        print(f"Добавлено: {title}")
    except sqlite3.IntegrityError:
        pass

# ================= ГЛАВНОЕ МЕНЮ =================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [InlineKeyboardButton(text=name, callback_data=MediaCallback(action="list", cat=key, page=0).pack())]
        for key, name in CATEGORY_TO_NAME.items()
    ]
    await message.answer("✝ Выберите тему:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ================= СПИСОК ФАЙЛОВ С ПАГИНАЦИЕЙ =================
PER_PAGE = 5

@dp.callback_query(MediaCallback.filter(F.action == "list"))
@dp.callback_query(MediaCallback.filter(F.action == "page"))
async def show_list(callback: types.CallbackQuery, callback_data: MediaCallback):
    cat = callback_data.cat
    page = callback_data.page
    offset = page * PER_PAGE

    cursor.execute("SELECT COUNT(*) FROM media WHERE category=?", (cat,))
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT id, title, media_type FROM media WHERE category=? ORDER BY added_at DESC LIMIT ? OFFSET ?",
        (cat, PER_PAGE, offset)
    )
    rows = cursor.fetchall()

    if not rows:
        await callback.answer("Пусто")
        return

    kb = []
    for item_id, title, mtype in rows:
        emoji = "🎥" if mtype == "video" else "🎵"
        text = f"{emoji} {title[:35]}..."
        kb.append([InlineKeyboardButton(
            text=text,
            callback_data=MediaCallback(action="play", cat=cat, item_id=item_id).pack()
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅ Назад", callback_data=MediaCallback(action="page", cat=cat, page=page-1).pack()))
    if offset + PER_PAGE < total:
        nav.append(InlineKeyboardButton("Дальше ➡", callback_data=MediaCallback(action="page", cat=cat, page=page+1).pack()))

    if nav:
        kb.append(nav)

    await callback.message.edit_text(
        f"{CATEGORY_TO_NAME[cat]}\nСтраница {page+1}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()

# ================= ВОСПРОИЗВЕДЕНИЕ =================
@dp.callback_query(MediaCallback.filter(F.action == "play"))
async def play_media(callback: types.CallbackQuery, callback_data: MediaCallback):
    cursor.execute("SELECT file_id, media_type, title FROM media WHERE id=?", (callback_data.item_id,))
    row = cursor.fetchone()

    if not row:
        await callback.answer("Файл не найден")
        return

    file_id, mtype, title = row

    if mtype == "video":
        await callback.message.answer_video(file_id, caption=title, supports_streaming=True)
    else:
        await callback.message.answer_audio(file_id, caption=title)

    await callback.answer("Отправляю...")

# ================= ЗАПУСК =================
async def main():
    print("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
