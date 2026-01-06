from asyncio import sleep
import re

from aiogram.utils.chat_action import ChatActionSender

from bot.controllers import user
from bot.controllers.base import refactor_string
from bot.controllers.base import imitate_typing
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.ai_client import AIClient
from bot.config import Settings
from bot.internal.enums import AIState, Form
from bot.handlers.ai import ai_assistant_photo_handler
from logging import getLogger

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from openai import BadRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai_client import AIClient
from bot.config import Settings
from bot.controllers.base import (
    refactor_string,
    validate_image_limit,
    validate_message_length,
)
from bot.controllers.gpt import get_or_create_ai_thread
from bot.controllers.user import check_action_limit
from bot.controllers.voice import process_voice
from bot.internal.enums import AIState
from bot.internal.keyboards import refresh_pictures_kb, subscription_kb
from bot.internal.lexicon import replies
from database.models import User
from database.models import PlantAnalysis
from sqlalchemy import select, desc
from pathlib import Path
from aiogram.types import FSInputFile
from bot.handlers.pdf_generator import generate_plan_pdf
import tempfile


router = Router()
logger = getLogger(__name__)
PHOTO_ANALYSIS_USER_TEXT = (
    "Если пользователь присылает первое фото, ты действуешь как строгий, но заботливый 'Доктор Хаус' для растений.\n"
    "Твоя задача: Проанализировать, напугать (если есть риск) или вдохновить (если все ок), чтобы продать решение.\n"
    "Формат ответа СТРОГО такой:\n"
    "📸 Анализ завершен.\n"
    "🌿 Пациент: [Название на латыни] ([Название на русском])\n"
    "📊 Health Score: [🔴/🟡/🟢] [Число]/10 ([Статус: Критическое/Среднее/Отличное])\n"
    "Диагноз Суслика:\n"
    "[2-3 предложения. Четко опиши симптомы, которые ты видишь на фото: пятна, тургор, цвет. Назови вероятную причину.]\n"
    "⚠️ Прогноз:\n"
    "[Что случится, если ничего не делать. Будь честным, но драматичным. Например: 'Без лечения сбросит листья за 2 недели'.]\n"
    "(Если растение здорово):\n"
    "Вердикт: Ты молодец! Но я вижу скрытый потенциал. [Опиши, как оно может вырасти лучше].\n"
    "Пиши уверенно и дружелюбно, без извинений и лишних пояснений."
    "В КОНЦЕ ответа добавь СТРОГО эти строки (без пояснений):"
    "PLANT: YES или NO"
    "QUALITY: GOOD или BAD"
)
PLAN_99_TEXT = ( """
### GENERATION PROTOCOL: ONE-TIME PAID PLAN (99₽)

Когда пользователь оплачивает разовый план, ты генерируешь "Персональную Карту Ухода".

Стиль:
– Строгий, медицинский (как рецепт врача)
– Без воды и общих фраз
– В конце — заботливый тон Суслика

Структура ответа строго фиксирована:

1. ЗАГОЛОВОК  
Эмодзи (🚑 для больных / 🚀 для здоровых) +  
Название: "Протокол Реанимации №{ID}" или "Карта Роста №{ID}"

2. ПАСПОРТ ПАЦИЕНТА  
– Название растения  
– Оценка здоровья (Score)  
– Основная проблема (1 строка)

3. ЭТАП 1: СРОЧНЫЕ МЕРЫ (Сделать сегодня)  
– Механическое действие  
– Точные измеримые инструкции

4. ЭТАП 2: АПТЕЧКА (Дешево и безопасно)  
– Только 1–2 доступных средства  
– Обязательно указать дозировку

5. ЭТАП 3: ГРАФИК НА 14 ДНЕЙ  
– Обязательно описать каждый день с 1 по 14  
– Формат строго: "День X: ..."

6. СЕКРЕТ СУСЛИКА  
– Один неочевидный лайфхак именно для этого растения

Ограничения:
– Не использовать общие фразы
– Не использовать дисклеймеры
– Не использовать эмодзи вне заголовков
– Не рекомендовать редкие или опасные вещества
"""
)

@router.message(AIState.WAITING_PLANT_PHOTO, F.text)
async def waiting_plant_photo_text(message: Message):
    await message.answer(
        "Я сейчас жду фото растения 📸\n"
        "Можешь просто отправить снимок при дневном свете 🌿"
    )

FLAG_RE = re.compile(r"^\s*(PLANT|QUALITY)\s*:\s*(YES|NO|GOOD|BAD)\s*$", re.IGNORECASE | re.MULTILINE)
@router.message(AIState.WAITING_PLANT_PHOTO, F.text)
async def DEBUG_ALL_TEXT(message: Message, state: FSMContext):
    current = await state.get_state()
    print("DEBUG TEXT:", message.text, "STATE:", current)

def extract_flags(text: str) -> tuple[str | None, str | None]:
    plant = None
    quality = None
    for m in FLAG_RE.finditer(text):
        key = m.group(1).upper()
        val = m.group(2).upper()
        if key == "PLANT":
            plant = val
        elif key == "QUALITY":
            quality = val
    return plant, quality

def strip_flags(text: str) -> str:
    cleaned = FLAG_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned

def extract_flag(text: str, flag: str) -> str | None:
    """
    Ищет строки вида:
    PLANT: YES
    QUALITY: BAD
    """
    match = re.search(rf"{flag}:\s*(YES|NO|GOOD|BAD)", text)
    return match.group(1) if match else None

from pathlib import Path


def response_to_blocks(text: str) -> list[str]:
    blocks = []
    current = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Заголовки этапов
        if line[0].isdigit() and "." in line[:3]:
            if current:
                blocks.append("<br>".join(current))
                current = []
            current.append(f"<h2>{line}</h2>")
        else:
            current.append(line)

    if current:
        blocks.append("<br>".join(current))

    return blocks






async def get_last_thread_id(db_session: AsyncSession, user_tg_id: int) -> str | None:
    stmt = (
        select(PlantAnalysis.thread_id)
        .where(PlantAnalysis.user_tg_id == user_tg_id)
        .order_by(desc(PlantAnalysis.created_at))
        .limit(1)
    )
    res = await db_session.execute(stmt)
    return res.scalar_one_or_none()

async def enter_waiting_plant_photo(message, state: FSMContext):
    await state.update_data(wait_reason="onboarding_plant_photo")
    await state.set_state(AIState.WAITING_PLANT_PHOTO)
    await message.answer(
        "📎 Пришли фото растения 📸\n"
        "Лучше при хорошем дневном свете и чтобы лист был крупно 🌿"
    )


@router.callback_query(F.data == "onb:send_photo")
async def onb_send_photo(callback: CallbackQuery, state: FSMContext):
    await enter_waiting_plant_photo(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "onb:demo")
async def onb_demo(callback: CallbackQuery, state: FSMContext):
    demo_image_path = "src/bot/data/demo_image_1.jpg"
    await callback.message.answer(
        "Давай я тебе покажу всю ту магию, которую я "
        "умею делать на примере. Вот фото реального растения,"
        "который нам присылал пользователь!"
    )
    await sleep(1)
    text = """👀 Смотри, какой тяжелый случай мне прислала Аня вчера.
    
    📸 Анализ завершен.
    🌿 Пациент: Zamioculcas zamiifolia (Замиокулькас)
    📊 Health Score: 😕 6/10 (Статус: Среднее)
    
    Диагноз Суслика:
    Вижу пожелтение и потерю яркости верхних листьев, часть выглядит пересушенной, отдельные пятна и светлые участки—признак избыточного полива или нехватки света. Возможны первые симптомы корневой гнили.
    
    ⚠️ Прогноз:
    Продолжение полива без просушки приведёт к массовому сбросу листьев, растение рискует погибнуть за 1–2 месяца.
    """

    await callback.message.answer_photo(
        photo = FSInputFile(demo_image_path),
        caption = text
    )
    await sleep(1)
    text = "А вот что с ним стало буквально через месяц нашего ухода!"
    demo_image_path = "src/bot/data/demo_image_2.jpg"
    await callback.message.answer_photo(
        photo=FSInputFile(demo_image_path),
        caption=text
    )
    await sleep(0.5)
        # await callback.message.answer(
     #   "Скажи мне когда ты будешь дома, чтобы ты смог прислать мне фото своих растений? Тогда мы сможем повторить эти упражнения уже на твоих растениях!"
   # )

    home_time_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Через 2 часа")],
            [KeyboardButton(text="🏠 Через 4 часа")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer(
        "Скажи мне, когда ты будешь дома, чтобы ты смог прислать фото своих растений.\n\n"
        "Тогда мы сможем повторить это упражнение уже на твоих растениях 🌿",
        reply_markup=home_time_kb
    )
    await state.set_state(AIState.WAITING_HOME_TIME)
    await callback.answer()

from datetime import datetime, timedelta
import asyncio
from aiogram.types import Message, ReplyKeyboardRemove


@router.message(
    AIState.WAITING_HOME_TIME,
    F.text.in_({"🏠 Через 2 часа", "🏠 Через 4 часа"})
)
async def handle_home_time(message: Message, state: FSMContext):
    if "2" in message.text:
        hours = 2
    else:
        hours = 4

    remind_at = datetime.utcnow() + timedelta(hours=hours)

    await message.answer(
        f"Отлично! Напомню через {hours} часа 😊",
        reply_markup=ReplyKeyboardRemove()
    )

    # 4. Планируем напоминание
    asyncio.create_task(
        schedule_reminder(
            message.bot,
            message.chat.id,
            remind_at
        )
    )

    # 5. Сбрасываем состояние (или можно перевести в другое)
    # await state.clear()

async def schedule_reminder(bot, chat_id: int, remind_at: datetime):
    delay = (remind_at - datetime.utcnow()).total_seconds()

    if delay > 0:
        await asyncio.sleep(delay)
    confirm_home_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, я дома", callback_data="home:yes")]
        ]
    )
    await bot.send_message(
        chat_id,
        "Привет! Ты уже дома? 🌿\n"
        "Мы можем начать анализировать твои растения — присылай фото 📸",
        reply_markup=confirm_home_kb
    )

from aiogram.types import CallbackQuery

@router.callback_query(F.data == "home:yes")
async def confirm_home(callback: CallbackQuery, state: FSMContext):
    await enter_waiting_plant_photo(callback.message, state)
    await callback.answer()


# @router.callback_query(F.data == "home:yes")
# async def confirm_home(callback: CallbackQuery, state: FSMContext):
    # 1. Подтверждаем
#    await callback.message.answer(
#        "Отлично! Тогда пришли фото растения 📸\n"
#        "Лучше при хорошем дневном свете 🌿"
#    )
#    await state.update_data(wait_reason="onboarding_plant_photo")
#    # 2. Переводим в нужное состояние
#    await state.set_state(AIState.WAITING_PLANT_PHOTO)
    # или WAITING_PHOTO, если заведёшь отдельное

#    await callback.answer()

from aiogram.types import Message

def extract_health_score(text: str) -> int | None:
    match = re.search(r'(\d{1,2})/10', text)
    return int(match.group(1)) if match else None
async def show_rescue_screen(message: Message, city: str):
    await message.answer(
        f"⚠️ Ситуация серьёзная, но растение можно спасти.\n\n"
        "Я подготовил для тебя экстренный 'Протокол Реанимации на 14 дней':\n"
        "💧 режим «сухого полива» (график)\n"
        "✂️ какие корни подрезать (схемы)\n"
        "💊 список дешёвых средств из аптеки\n\n"
        "Забери план и спаси растение 👇",
        reply_markup=RESCUE_KB
    )


async def show_growth_screen(message: Message, city: str):

    await message.answer(
        f"🌿 Растение в хорошем состоянии!\n\n"
        "Хочешь перевести его в режим **«Активный рост»**?\n\n"
        "✅ Что ты получишь:\n"
        f"• умные напоминания под погоду в {city}\n"
        "• схему подкормки для крупных листьев\n"
        "• алерты при опасной влажности\n\n"
        "Я могу следить за растением 24/7 👇",
        reply_markup=GROWTH_KB,
    )


RESCUE_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🚑 Начать лечение за 390₽", callback_data="pay:rescue")],
    [InlineKeyboardButton(text="📄 Получить план разово за 99₽", callback_data="pay:rescue_once")],
    [InlineKeyboardButton(text="🙅 Оставить как есть", callback_data="skip")]
])

GROWTH_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🚀 Активировать Умный Уход за 390₽", callback_data="pay:growth")],
    [InlineKeyboardButton(text="🙅 Оставить как есть", callback_data="skip")]
])



@router.message(AIState.WAITING_PLANT_PHOTO, F.voice)
async def waiting_plant_photo_voice(message: Message):
    await message.answer(
        "Понял тебя 😊\n"
        "Но для анализа мне нужно фото растения 📸"
    )

@router.message(AIState.WAITING_PLANT_PHOTO, F.photo)
async def handle_plant_photo(
    message: Message,
    state: FSMContext,
    openai_client: AIClient,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
):
    # 1️⃣ Получаем / создаём AI-thread
    thread_id = await get_or_create_ai_thread(user, openai_client, db_session)

    # 2️⃣ Забираем bytes изображения
    photo = message.photo[-1]
    file_info = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file_info.file_path)
    image_bytes = file_bytes.read()

    # 3️⃣ Отправляем фото в AI
    async with ChatActionSender.typing(
        bot=message.bot,
        chat_id=message.chat.id
    ):
        response = await openai_client.get_response_with_image(
            thread_id=thread_id,
            text=PHOTO_ANALYSIS_USER_TEXT,
            image_bytes=image_bytes,
            message=message,
            fullname=user.fullname,
        )

    # 4️⃣ Если AI вернул ошибку или пустой ответ — остаёмся в WAITING_PLANT_PHOTO
    if (
        not response
        or response.startswith("Превышены лимиты")
        or response.startswith("Ошибка при обработке изображения")
    ):
        await message.answer(
            "Не получилось проанализировать фото 😔\n"
            "Попробуй сфотографировать растение ещё раз при хорошем дневном свете 📸"
        )
        return  # ❗ остаёмся в WAITING_PLANT_PHOTO

    # 5️⃣ Чистим ответ
    cleaned = response
    plant_flag, quality_flag = extract_flags(cleaned)
    # 6️⃣ Пытаемся извлечь Health Score

    cleaned_for_user = strip_flags(cleaned)
    # 7️⃣ Если Health Score нет — считаем фото невалидным
    # 🚫 На фото не растение
    if plant_flag != "YES":
        await message.answer(
            "Я не уверен, что на фото растение 🌱\n"
            "Пришли, пожалуйста, фото именно растения 📸"
        )
        return  # остаёмся в WAITING_PLANT_PHOTO

    score = extract_health_score(cleaned)

    # страховка, если модель сломалась
    if score is None:
        await message.answer(
            "Я смог распознать растение, но не уверен в оценке состояния 😔\n"
            "Попробуй прислать фото ещё раз при хорошем освещении 📸"
        )
        return
    analysis = PlantAnalysis(
        user_tg_id=user.tg_id,  # или user.id — как у тебя принято
        thread_id=thread_id,
        tg_file_id=photo.file_id,
        tg_file_unique_id=photo.file_unique_id,
        ai_response=cleaned,
        health_score=score,
    )
    db_session.add(analysis)
    await db_session.commit()

    scenario = "rescue" if score <= 5 else "growth"
    await state.update_data(onboarding_scenario=scenario, health_score=score)
    await message.answer(cleaned_for_user)
    await sleep(1)
    print("Обвал тут")
    await state.set_state(AIState.WAITING_CITY)

    if score <= 5:
        await message.answer(
            "⚠️ Похоже, растению нужна помощь.\n"
            "Чтобы я рассчитал уход под твой климат, напиши свой город 🌍"
        )
    else:
        await message.answer(
            "✅ В целом растение чувствует себя неплохо!\n"
            "Чтобы я рассчитал уход под твой климат, напиши свой город 🌍"
        )




'''@router.message(AIState.WAITING_PLANT_PHOTO, F.photo)
async def handle_plant_photo(
    message: Message,
    state: FSMContext,
    openai_client: AIClient,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
):
    # 1. Подменяем caption

    # 2. Переводим в обычный режим
    await state.set_state(AIState.IN_AI_DIALOG)

    # 3. ЯВНО вызываем основной фото-хендлер
    await ai_assistant_photo_handler(
        message=message,
        openai_client=openai_client,
        user=user,
        settings=settings,
        db_session=db_session,
        forced_user_text=PHOTO_ANALYSIS_USER_TEXT,
    )'''

@router.message(
    Form.geography,
    F.text,
)
async def handle_geography(message: Message, state: FSMContext, user: User, db_session: AsyncSession):
    city = message.text.strip()
    user.geography = city
    await db_session.commit()
    data = await state.get_data()
    scenario = data.get("onboarding_scenario")

    # DEBUG на время
    await message.answer(f"(debug) scenario={scenario}")
   # await state.set_state(AIState.IN_AI_DIALOG)

    if scenario == "rescue":
        await show_rescue_screen(message, city)
    elif scenario == "growth":
        await show_growth_screen(message, city)
    else:
        await show_rescue_screen(message, city)
    await state.set_state(AIState.IN_AI_DIALOG)

@router.message(AIState.WAITING_CITY, F.text)
async def handle_city(message: Message, state: FSMContext, user: User, db_session: AsyncSession):
    city = message.text.strip()
    user.geography = city
    await db_session.commit()
    data = await state.get_data()
    scenario = data.get("onboarding_scenario")

    if scenario == "rescue":
        await show_rescue_screen(message, city)
    else:
        await show_growth_screen(message, city)
    await state.set_state(AIState.IN_AI_DIALOG)

@router.callback_query(F.data == "skip")
async def handle_skip_onboarding(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    db_session: AsyncSession,
openai_client=None):
    #  ️Устанавливаем action_count = 3
    if user.ai_thread:
        await openai_client.delete_thread(user.ai_thread)
        user.ai_thread = None
    user.action_count += 3
    await db_session.commit()

    # Переводим в основной режим
    await state.set_state(AIState.IN_AI_DIALOG)

    # Сообщение пользователю
    await callback.message.answer(
        "🌱 Дорогой друг,\n\n"
        "У тебя осталось ещё 2 попытки.\n"
        "Ты можешь задать любой вопрос 💬\n"
        "или отправить фото растения 📸"
    )

    # Убираем «часики» у кнопки
    await callback.answer()

from aiogram.types import Message
from aiogram.types import FSInputFile

async def show_subscription_paywall(
    message: Message,
    user: User,
    settings: Settings,
):
    await message.forward(settings.bot.CHAT_LOG_ID)

    await message.answer_photo(
        FSInputFile(path="src/bot/data/greetings.png"),
        replies["action_limit_exceeded"],
        reply_markup=subscription_kb(),
    )

    log_text = replies["action_limit_exceeded_log"].format(
        username=user.username
    )
    logger.info(log_text)

    await message.bot.send_message(
        settings.bot.CHAT_LOG_ID,
        log_text,
    )

@router.callback_query(F.data.in_(["pay:rescue", "pay:growth"]))
async def handle_paywall_from_onboarding(
    callback: CallbackQuery,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
    openai_client=None
):
    if user.ai_thread:
        await openai_client.delete_thread(user.ai_thread)
        user.ai_thread = None
    user.action_count = 5
    await db_session.commit()
    await show_subscription_paywall(
        message=callback.message,
        user=user,
        settings=settings,
    )

    await callback.answer()

async def build_rescue_plan(
    message: Message,
    user: User,
    db_session: AsyncSession,
    openai_client: AIClient,
):
    # 1️⃣ Берём последний анализ
    stmt = (
        select(PlantAnalysis)
        .where(PlantAnalysis.user_tg_id == user.tg_id)
        .order_by(desc(PlantAnalysis.created_at))
        .limit(1)
    )
    result = await db_session.execute(stmt)
    analysis = result.scalar_one_or_none()

    if not analysis:
        await message.answer(
            "Я не нашёл анализа растения 🌱\n"
            "Сначала пришли фото растения 📸"
        )
        return

    # 2️⃣ Показываем исходные данные
    await message.answer(
        "Я подготовлю персональный план ухода на основе этого анализа 👇"
    )

    await message.answer_photo(
        photo=analysis.tg_file_id,
        caption="📸 Фото, на котором основан план"
    )

    if not analysis.thread_id:
        await message.answer("Ошибка: не найден AI-диалог 😔")
        return

    # 3️⃣ Скачиваем изображение
    file_info = await message.bot.get_file(analysis.tg_file_id)
    file_bytes = await message.bot.download_file(file_info.file_path)
    image_bytes = file_bytes.read()

    # 4️⃣ OpenAI
    response = await openai_client.get_response_with_image(
        thread_id=analysis.thread_id,
        text=PLAN_99_TEXT,
        image_bytes=image_bytes,
        message=message,
        fullname=user.fullname,
    )

    # 5️⃣ PDF
    tmp_dir = Path(tempfile.gettempdir())
    pdf_path = tmp_dir / f"plan_{analysis.id}.pdf"

    generate_plan_pdf(
        response_text=response,
        output_path=str(pdf_path),
        title=f"Протокол Реанимации №{analysis.id}",
    )

    # 6️⃣ Отправляем пользователю
    await message.answer_document(
        FSInputFile(pdf_path),
        caption="📄 Твой персональный план ухода готов 🌱"
    )

    await message.answer(response)



@router.callback_query(F.data == "pay:rescue_once")
async def recipe_analysis(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    db_session: AsyncSession,
    openai_client: AIClient,
):
    # 🔹 закрываем callback МГНОВЕННО
    await callback.answer("Готовлю план 🌱")

    # 🔹 информируем пользователя
    await callback.message.answer(
        "Я готовлю персональный план ухода 🌿\n"
        "Это может занять до минуты."
    )

    # 🔹 запускаем тяжёлую логику
    await build_rescue_plan(
        message=callback.message,
        user=user,
        db_session=db_session,
        openai_client=openai_client,
    )

