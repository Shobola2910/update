import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv
from groq import AsyncGroq

from prompts import SYSTEM_PROMPT

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

logging.basicConfig(level=logging.INFO)

groq_client = AsyncGroq(api_key=GROQ_API_KEY)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

LANGUAGES = {
    "uz": ("🇺🇿 UZB", "Javobni o'zbek tilida yozing."),
    "ru": ("🇷🇺 RUS", "Ответ напиши на русском языке."),
    "en": ("🇬🇧 ENG", "Write the response in English."),
}

pending_requests: dict[int, str] = {}


def language_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"lang:{code}")
        for code, (label, _) in LANGUAGES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Salom! Men Algo Service yordamchi botiman.\n\n"
        "Menga quyidagi formatda yozing:\n"
        "Ism, Muammo\n\n"
        "Masalan: Ali, ELD disconnected"
    )


@dp.message(F.text)
async def receive_request(message: Message) -> None:
    user_input = message.text.strip()

    if "," not in user_input:
        await message.answer(
            "Iltimos, ma'lumotni quyidagi formatda yuboring:\n"
            "Ism, Muammo\n\n"
            "Masalan: Ali, ELD disconnected"
        )
        return

    pending_requests[message.chat.id] = user_input
    await message.answer("Qaysi tilda xabar tayyorlansin?", reply_markup=language_keyboard())


@dp.callback_query(F.data.startswith("lang:"))
async def generate_message(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id
    user_input = pending_requests.get(chat_id)

    if user_input is None:
        await callback.answer("So'rov topilmadi, iltimos qaytadan yuboring.", show_alert=True)
        return

    lang_code = callback.data.split(":", 1)[1]
    _, lang_instruction = LANGUAGES[lang_code]

    await callback.answer()
    await bot.send_chat_action(chat_id, "typing")

    try:
        response = await groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_input}\n\n{lang_instruction}"},
            ],
        )
        result_text = response.choices[0].message.content.strip()
    except Exception:
        logging.exception("Groq API xatosi")
        await callback.message.answer(
            "Kechirasiz, xabar tayyorlashda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring."
        )
        return

    await callback.message.answer(result_text)
    pending_requests.pop(chat_id, None)


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def start_web_server() -> None:
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main() -> None:
    await start_web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
