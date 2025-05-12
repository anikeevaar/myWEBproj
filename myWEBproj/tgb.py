import asyncio
import logging

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message

from config import BOT_TOKEN  # импортируем токен

form_router = Router()
dp = Dispatcher()
logger = logging.getLogger(__name__)


class Form(StatesGroup):
    weather = State()
    locality = State()


@form_router.message(CommandStart())
async def command_start(message: Message, state: FSMContext):
    await state.set_state(Form.locality)
    await message.answer(
        "Привет. Пройдите небольшой опрос, пожалуйста!\n"
        "Вы можете прервать опрос, послав команду /stop.\n"
        "В каком городе вы живёте?",
    )


@form_router.message(Command("stop"))
@form_router.message(F.text.casefold() == "stop")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info("Остановились на шаге %r", current_state)
    await state.clear()
    await message.answer(
        "Всего доброго!",
    )


@form_router.message(Form.locality)
async def process_locality(message: Message, state: FSMContext):
    await state.set_state(Form.weather)
    locality = message.text
    await state.update_data(locality=locality) # сохраняем введенные данные во внутреннем хранилище
    await message.answer(
        f"Какая погода в городе {locality}?")


@form_router.message(Form.weather)
async def process_weather(message: Message, state: FSMContext):
    data = await state.get_data() # получаем ранее сохраненные данные из внутреннего хранилища
    await state.clear()
    weather = message.text
    logger.info(f"погода {weather}")
    await message.answer(
        f"Спасибо за участие в опросе! Привет, {data['locality']}!")


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp.include_router(form_router)
    await dp.start_polling(bot)


if __name__ == '__main__':
    # Запускаем логгирование
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG
    )
    asyncio.run(main())  # начинаем принимать сообщения