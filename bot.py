import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# BOT TOKENINGIZNI SHU YERGA YOZING
API_TOKEN = "8793661108:AAGZwGEqGAlxp8aFcURDwjOBMs-ayh9zkxU"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

user_states = {} 
user_tasks = {} 

# TUGMALAR MATNI ANIQ QILINDI
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Vazifa qo'shish")],
        [KeyboardButton(text="Mening eslatmalarim")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_tasks:
        user_tasks[user_id] = []
    user_states[user_id] = {}
    await message.answer(
        "Assalomu alaykum! Men Suhrob Reminder Botman.\n"
        "Eslatmalaringizni aniq vaqtida yuboraman.",
        reply_markup=main_menu
    )

# 1. VAZIFA QO'SHISH BOSHLANISHI
@dp.message(F.text == "Vazifa qo'shish")
async def add_task_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = {"step": "waiting_for_name"}
    await message.answer(
        "Yangi vazifa nomini yozing:", 
        reply_markup=ReplyKeyboardRemove()
    )

# 2. NOMNI QABUL QILISH
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("step") == "waiting_for_name")
async def process_task_name(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id]["task_name"] = message.text
    user_states[user_id]["step"] = "waiting_for_time"
    await message.answer("Qachon eslatma kelsin? (Masalan: Ertaga 15:00)")

# 3. VAQTNI QABUL QILISH VA SAQLASH
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("step") == "waiting_for_time")
async def process_task_time(message: types.Message):
    user_id = message.from_user.id
    time_input = message.text.lower()
    task_name = user_states[user_id].get("task_name", "Vazifa")
    
    target_time = None
    now = datetime.now()
    
    if "ertaga" in time_input:
        target_date = now + timedelta(days=1)
        try:
            h, m_val = map(int, time_input.split()[-1].split(':'))
            target_time = target_date.replace(hour=h, minute=m_val, second=0)
        except: pass
    elif "bugun" in time_input:
        try:
            h, m_val = map(int, time_input.split()[-1].split(':'))
            target_time = now.replace(hour=h, minute=m_val, second=0)
            if target_time < now: target_time += timedelta(days=1)
        except: pass
            
    if target_time:
        job_id = f"task_{user_id}_{int(now.timestamp())}"
        scheduler.add_job(send_reminder, 'date', run_date=target_time, args=[user_id, task_name], id=job_id)
        
        if user_id not in user_tasks: user_tasks[user_id] = []
        user_tasks[user_id].append({
            "name": task_name, 
            "time": target_time.strftime("%d-%m %H:%M"), 
            "job_id": job_id
        })
        
        await message.answer(f"✅ Qabul! {target_time.strftime('%H:%M')} da eslataman.", reply_markup=main_menu)
        user_states[user_id] = {}
    else:
        await message.answer("Vaqt tushunilmadi. Iltimos 'Ertaga 15:00' formatida yozing.")

# 4. MENING ESLATMALARIM (INLINE TUGMALAR BILAN)
@dp.message(F.text == "Mening eslatmalarim")
async def show_tasks(message: types.Message):
    user_id = message.from_user.id
    tasks = user_tasks.get(user_id, [])
    
    if not tasks:
        await message.answer("Hozirda faol eslatmalar yo'q.")
        return
        
    text = "📝 Sizning eslatmalaringiz:\n\n"
    for i, task in enumerate(tasks, 1):
        text += f"{i}. {task['name']}— {task['time']}\n"
        
    # Inline tugmalar yaratish
    keyboard = []
    for i, task in enumerate(tasks):
        keyboard.append([
            InlineKeyboardButton(text=f"✏️ Tahrirlash", callback_data=f"edit_{i}"),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"delete_{i}")
        ])
        
    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

# 5. O'CHIRISH FUNKSIYASI
@dp.callback_query(F.data.startswith("delete_"))
async def delete_task(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    index = int(callback.data.split("_")[1])
    tasks = user_tasks.get(user_id, [])
    
    if 0 <= index < len(tasks):
        job_id = tasks[index]["job_id"]
        try:
            scheduler.remove_job(job_id)
        except: pass
        
        tasks.pop(index)
        user_tasks[user_id] = tasks
        await callback.answer("Eslatma o'chirildi!")
        
        # Ro'yxatni yangilash
        if tasks:
            await show_tasks(callback.message)
        else:
            await callback.message.edit_text("Hozirda faol eslatmalar yo'q.")
    else:
        await callback.answer("Xatolik yuz berdi.")

# 6. TAHRIRLASH BOSHLANISHI
@dp.callback_query(F.data.startswith("edit_"))
async def edit_task(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    index = int(callback.data.split("_")[1])
    tasks = user_tasks.get(user_id, [])
    
    if 0 <= index < len(tasks):
        user_states[user_id] = {"step": "editing", "index": index}
        await callback.answer("Yangi nomni yozing:")
        await bot.send_message(user_id, "Yangi vazifa nomini kiriting:", reply_markup=ReplyKeyboardRemove())
    else:
        await callback.answer("Xatolik.")

# 7. YANGI NOMNI QABUL QILISH
@dp.message(lambda m: user_states.get(m.from_user.id, {}).get("step") == "editing")
async def process_edit_name(message: types.Message):
    user_id = message.from_user.id
    index = user_states[user_id]["index"]
    new_name = message.text
    tasks = user_tasks[user_id]
    
    old_job_id = tasks[index]["job_id"]
    old_time_str = tasks[index]["time"]
    
    # Eski jobni o'chirish
    try:
        scheduler.remove_job(old_job_id)
    except: pass
    
    # Yangi job yaratish
    try:
        day, time_part = old_time_str.split(" ")
        d, m_val = map(int, day.split("-"))
        h, min_val = map(int, time_part.split(":"))
        
        now = datetime.now()
        target_time = now.replace(day=d, month=m_val, hour=h, minute=min_val, second=0)
        if target_time < now:
            target_time = target_time.replace(year=now.year + 1)
            
        new_job_id = f"task_{user_id}_{int(now.timestamp())}"
        scheduler.add_job(send_reminder, 'date', run_date=target_time, args=[user_id, new_name], id=new_job_id)
        
        tasks[index] = {"name": new_name, "time": old_time_str, "job_id": new_job_id}
        user_tasks[user_id] = tasks
        
        await message.answer(f"✅ Tahrirlandi: {new_name}", reply_markup=main_menu)
        user_states[user_id] = {}
    except Exception as e:
        logger.error(f"Tahrirlash xatosi: {e}")
        await message.answer("Xatolik yuz berdi.")

async def send_reminder(user_id, task_name):
    try:
        await bot.send_message(user_id, f" <b>Eslatma!</b>\n\n{task_name} vaqti yetib keldi!")
    except Exception as e:
        logger.error(f"Eslatma xatosi: {e}")

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())