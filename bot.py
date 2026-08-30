import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

# TOKENNI SHU YERGA YOZING
API_TOKEN = "8793661108:AAGZwGEqGAlxp8aFcURDwjOBMs-ayh9zkxU"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

# --- DATABASE SOZLAMALARI ---
DB_NAME = "reminders.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER, 
                  task_name TEXT, 
                  target_time TEXT, 
                  job_id TEXT)''')
    conn.commit()
    conn.close()

def add_task_to_db(user_id, task_name, target_time_str, job_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO tasks (user_id, task_name, target_time, job_id) VALUES (?, ?, ?, ?)",
              (user_id, task_name, target_time_str, job_id))
    conn.commit()
    conn.close()

def get_user_tasks(user_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE user_id = ?", (user_id,))
    tasks = [dict(row) for row in c.fetchall()]
    conn.close()
    return tasks

def delete_task_from_db(job_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()

# Database ni ishga tushirish
init_db()

# Ma'lumotlar bazasi (faqat vaqtinchalik holat uchun)
user_states = {}

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Vazifa qo'shish")],
        [KeyboardButton(text="Mening eslatmalarim")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_states[message.from_user.id] = {}
    await message.answer(
        "Assalomu alaykum! Men  Reminder Botman.\n"
        "Eslatmalaringiz endi xavfsiz saqlanadi.",
        reply_markup=main_menu
    )

@dp.message(F.text == "Vazifa qo'shish")
async def add_task_start(message: types.Message):
    user_states[message.from_user.id] = {"step": "waiting_for_name"}
    await message.answer("Yangi vazifa nomini yozing:", reply_markup=ReplyKeyboardRemove())

@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("step") == "waiting_for_name")
async def process_task_name(message: types.Message):
    user_states[message.from_user.id]["task_name"] = message.text
    user_states[message.from_user.id]["step"] = "waiting_for_time"
    await message.answer("Qachon eslatma kelsin? (Masalan: Bugun 15:00)")

@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("step") == "waiting_for_time")
async def process_task_time(message: types.Message):
    user_id = message.from_user.id
    time_input = message.text.lower().strip()
    task_name = user_states[user_id].get("task_name", "Vazifa")
    
    target_time = None
    now = datetime.now()
    
    try:
        if "ertaga" in time_input:
            target_date = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            h, m = map(int, time_input.split()[-1].split(':'))
            target_time = target_date.replace(hour=h, minute=m)
        elif "bugun" in time_input:
            h, m = map(int, time_input.split()[-1].split(':'))
            target_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target_time <= now: target_time += timedelta(days=1)
        else:
            h, m = map(int, time_input.split(':'))
            target_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target_time <= now: target_time += timedelta(days=1)
    except:
        await message.answer("Vaqt formati noto'g'ri. 'Bugun 15:00' deb yozing.")
        return

    if target_time:
        job_id = f"task_{user_id}_{int(now.timestamp())}"
        
        # Scheduler ga qo'shish
        scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=target_time), 
                          args=[user_id, task_name], id=job_id, replace_existing=True)
        
        # Bazaga yozish
        add_task_to_db(user_id, task_name, target_time.strftime("%d-%m %H:%M"), job_id)
        
        await message.answer(f"✅ Qabul! {target_time.strftime('%H:%M')} da eslataman.", reply_markup=main_menu)
        user_states[user_id] = {}

async def send_reminder(user_id, task_name):
    try:
        await bot.send_message(user_id, f"🔔 Eslatma!\n\n{task_name} vaqti yetib keldi!")
        # Eslatma yuborilgandan keyin bazadan o'chirish (ixtiyoriy)
        # delete_task_from_db(...) 
    except Exception as e:
        logger.error(f"Eslatma xatosi: {e}")

@dp.message(F.text == "Mening eslatmalarim")
async def show_tasks(message: types.Message):
    tasks = get_user_tasks(message.from_user.id)
    
    if not tasks:
        await message.answer("Hozirda faol eslatmalar yo'q.")
        return
        
    text = "📝Sizning eslatmalaringiz:\n\n"
    keyboard = []
    
    for i, task in enumerate(tasks):
        text += f"{i+1}. {task['task_name']} — {task['target_time']}\n"
        keyboard.append([
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"delete_{task['job_id']}")
        ])
        
    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data.startswith("delete_"))
async def delete_task(callback: types.CallbackQuery):
    job_id = callback.data.split("_", 1)[1]
    try: scheduler.remove_job(job_id)
    except: pass
    
    delete_task_from_db(job_id)
    await callback.answer("O'chirildi!")
    await show_tasks(callback.message)

async def main():
    # Bot qayta ishga tushganda eski vazifalarni tiklash
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    
    for task in tasks:
        try:
            run_date = datetime.strptime(task['target_time'], "%d-%m %H:%M")
            if run_date.year == datetime.now().year: # Oddiy tekshiruv
                 scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=run_date), 
                                  args=[task['user_id'], task['task_name']], id=task['job_id'], replace_existing=True)
        except: pass
            
    scheduler.start()
    logger.info("Bot va Database ishga tushdi.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())