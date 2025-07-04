import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputFile

from sqlalchemy import Column, Integer, String, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import pandas as pd
import json

# --- Конфигурация ---
API_TOKEN = '7578176652:AAH852GBmfiZgVXjaNRJq0hHNjHrOnogKsw'
ADMIN_ID = 12091391

# --- База данных ---
Base = declarative_base()
engine = create_engine('sqlite:///test_bot.db')
SessionLocal = sessionmaker(bind=engine)

class UserResult(Base):
    __tablename__ = 'results'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    full_name = Column(String)
    language = Column(String)
    score_percent = Column(Integer)
    passed = Column(Boolean)

Base.metadata.create_all(engine)

# --- FSM состояния ---
class TestStates(StatesGroup):
    choosing_language = State()
    entering_name     = State()
    answering         = State()

# --- Загрузка вопросов ---
with open('questions.json', encoding='utf-8') as f:
    QUESTIONS = json.load(f)

# --- Инициализация бота ---
storage = MemoryStorage()
bot     = Bot(token=API_TOKEN)
dp      = Dispatcher(storage=storage)

# --- Языковая клавиатура ---
languages_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Русский"), KeyboardButton(text="O'zbek")]],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await message.answer("Выберите язык / Tilni tanlang:", reply_markup=languages_kb)
    await state.set_state(TestStates.choosing_language)

@dp.message(TestStates.choosing_language)
async def process_language(message: types.Message, state: FSMContext):
    await state.update_data(language=message.text)
    await message.answer("Введите ФИО: / FISh kiritin", reply_markup=ReplyKeyboardRemove())
    await state.set_state(TestStates.entering_name)

@dp.message(TestStates.entering_name)
async def process_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['language']
    await state.update_data(full_name=message.text, current=0, correct=0)
    q = QUESTIONS[0]
    opts = q['options'] if lang == 'Русский' else q['options_uz']
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=o)] for o in opts], resize_keyboard=True)
    text = q['question'] if lang == 'Русский' else q['question_uz']
    await message.answer(text, reply_markup=kb)
    await state.set_state(TestStates.answering)

@dp.message(TestStates.answering)
async def process_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['language']
    idx = data['current']
    q = QUESTIONS[idx]
    correct_ans = q['correct'] if lang == 'Русский' else q['correct_uz']
    if message.text == correct_ans:
        data['correct'] += 1
    data['current'] += 1
    if data['current'] < len(QUESTIONS):
        q = QUESTIONS[data['current']]
        opts = q['options'] if lang == 'Русский' else q['options_uz']
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=o)] for o in opts], resize_keyboard=True)
        text = q['question'] if lang == 'Русский' else q['question_uz']
        await state.update_data(current=data['current'], correct=data['correct'])
        await message.answer(text, reply_markup=kb)
    else:
        percent = int(data['correct'] / len(QUESTIONS) * 100)
        passed = percent >= 60
        await message.answer(f"Результат: {percent}%. {'Прошел' if passed else 'Не прошел'}.", reply_markup=ReplyKeyboardRemove())
        db = SessionLocal()
        db.add(UserResult(
            user_id=message.from_user.id,
            full_name=data['full_name'],
            language=lang,
            score_percent=percent,
            passed=passed
        ))
        db.commit()
        db.close()
        await state.clear()

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return
    db = SessionLocal()
    recs = db.query(UserResult).all()
    db.close()
    if not recs:
        await message.answer("Нет результатов.")
        return
    lines = [f"{r.full_name} ({r.language}): {r.score_percent}% - {'OK' if r.passed else 'Fail'}" for r in recs]
    await message.answer("\n".join(lines))

@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if message.from_user.id != ADMIN_ID or message.chat.type != "private":
        return
    df = pd.read_sql_table('results', con=engine)
    path = 'results.xlsx'
    df.to_excel(path, index=False)
    await message.answer_document(InputFile(path))

# --- Запуск ---
if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))