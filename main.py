import asyncio
import glob
import json
import os
import wave

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
from vosk import Model, KaldiRecognizer

from logger_config import get_logger

# Загрузка переменных из файла .env
load_dotenv()

# Чтение переменных из окружения
API_TOKEN = os.getenv('API_TOKEN')
CONVERTIO_API_KEY = os.getenv('CONVERTIO_API_KEY')

if not API_TOKEN or not CONVERTIO_API_KEY:
    raise ValueError("Не удалось загрузить переменные API_TOKEN или CONVERTIO_API_KEY из файла .env")

# Подключение логгера
logger = get_logger()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Инициализация Vosk
model = Model("vosk-model-small-ru")


async def convert_voice_to_text(file_path: str):
    """
    Конвертирует голосовой файл в текст с помощью внешнего API Convertio.

    :param file_path: URL-адрес файла, который нужно конвертировать.
    :raises ValueError: Если API возвращает ошибку на любом этапе.
    """
    logger.info(f"Начата конвертация файла: {file_path}")
    # Логируем информацию о начале процесса конвертации файла.

    async with aiohttp.ClientSession() as session:
        # Открываем асинхронную сессию для выполнения HTTP-запросов.

        # Отправка запроса на конвертацию файла.
        async with session.post(
                'https://api.convertio.co/convert',
                json={
                    'apikey': CONVERTIO_API_KEY,  # API-ключ для авторизации.
                    'input': 'url',  # Указываем, что передаём URL.
                    'file': file_path,  # URL-адрес исходного файла.
                    'outputformat': 'wav'  # Желаемый формат файла на выходе.
                }
        ) as response:
            # Делаем POST-запрос к API Convertio с параметрами конвертации.
            response_data = await response.json()
            # Читаем и парсим JSON-ответ от API.
            logger.debug(f"Ответ от Convertio на запрос конвертации: {response_data}")
            # Логируем полный ответ для отладки.

            if 'data' not in response_data:
                # Проверяем, содержит ли ответ ключ 'data'.
                error_msg = response_data.get('error', 'Неизвестная ошибка')
                # Если 'data' отсутствует, пытаемся получить сообщение об ошибке.
                logger.error(f"Ошибка при начальной конвертации: {error_msg}")
                # Логируем ошибку.
                raise ValueError(f"Ошибка при конвертации файла: {error_msg}")
                # Выбрасываем исключение, так как конвертация не началась.

            conversion_id = response_data['data']['id']
            # Получаем идентификатор процесса конвертации.
            logger.info(f"Конвертация начата, ID конвертации: {conversion_id}")
            # Логируем ID для отслеживания статуса.

        # Ожидание завершения конвертации.
        while True:
            async with session.get(
                    f'https://api.convertio.co/convert/{conversion_id}/status',
                    params={'apikey': CONVERTIO_API_KEY}
                    # Делаем GET-запрос для проверки статуса конвертации.
            ) as response:
                status_data = await response.json()
                # Читаем и парсим JSON-ответ от API.
                logger.debug(f"Статус конвертации: {status_data}")
                # Логируем статус для отладки.

                if status_data['data']['step'] == 'finish':
                    # Проверяем, завершён ли процесс конвертации.
                    file_url = status_data['data']['output']['url']
                    # Получаем URL готового файла.
                    logger.info(f"Конвертация завершена. URL файла: {file_url}")
                    # Логируем успешное завершение конвертации.
                    break
                if status_data['data']['step'] == 'error':
                    # Проверяем, не возникла ли ошибка во время конвертации.
                    error_msg = status_data['data'].get('error', 'Неизвестная ошибка')
                    # Получаем сообщение об ошибке.
                    logger.error(f"Ошибка конвертации: {error_msg}")
                    # Логируем ошибку.
                    raise ValueError(f"Ошибка конвертации: {error_msg}")
                    # Выбрасываем исключение.

            await asyncio.sleep(5)
            # Если процесс ещё не завершён, ждём 5 секунд перед следующим запросом.

        # Скачивание готового файла.
        async with session.get(file_url) as response:
            # Делаем GET-запрос для загрузки готового файла.
            audio_content = await response.read()
            # Читаем содержимое файла.
            logger.info("Аудиофайл успешно скачан")
            # Логируем успешное скачивание.

    # Сохранение файла на диск.
    with open('voice_message.wav', 'wb') as f:
        # Открываем файл для записи в бинарном режиме.
        f.write(audio_content)
        # Записываем содержимое аудиофайла.
        logger.info("Файл сохранён как voice_message.wav")
        # Логируем успешное сохранение файла.


@dp.message(Command("start"))
async def send_welcome(message: Message):
    """
    Обрабатывает команду /start. Отправляет приветственное сообщение.

    :param message: Объект сообщения от пользователя.
    """
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}")
    await message.answer("Привет! Отправьте мне голосовое сообщение, и я попробую распознать его.")


@dp.message(F.voice)
async def handle_voice(message: Message):
    """
    Обрабатывает голосовые сообщения, загружает файл, конвертирует его
    и распознаёт текст с помощью Vosk.

    :param message: Объект голосового сообщения.
    """
    # Логируем, что получили голосовое сообщение, и указываем ID пользователя.
    logger.info(f"Получено голосовое сообщение от пользователя {message.from_user.id}")

    # Получаем идентификатор файла голосового сообщения.
    file_id = message.voice.file_id

    # Запрашиваем подробности о файле у Telegram API.
    file = await bot.get_file(file_id)

    # Извлекаем путь к файлу из объекта file.
    file_path = file.file_path

    # Формируем полный URL для загрузки файла.
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"

    # Логируем URL файла для отладки.
    logger.info(f"Ссылка на файл: {file_url}")

    # Создаём асинхронную сессию для выполнения HTTP-запросов.
    async with aiohttp.ClientSession() as session:

        # Загружаем голосовой файл с указанного URL.
        async with session.get(file_url) as response:
            # Читаем содержимое файла в виде бинарных данных.
            audio_content = await response.read()

            # Логируем успешное завершение загрузки файла.
            logger.info("Аудиофайл успешно загружен")

        # Открываем файл `voice_message.ogg` для записи в бинарном режиме.
    with open('voice_message.ogg', 'wb') as f:

        # Сохраняем загруженное содержимое в файл.
        f.write(audio_content)

        # Логируем, что файл успешно сохранён.
        logger.info("Файл сохранён как voice_message.ogg")

    try:
        # Пытаемся конвертировать голосовой файл в текстовый формат с помощью функции `convert_voice_to_text`.
        await convert_voice_to_text(file_url)

        # Обрабатываем возможное исключение ValueError, если возникла ошибка при конвертации.
    except ValueError as e:

        # Логируем возникшую ошибку.
        logger.error(f"Ошибка во время конвертации: {e}")

        # Отправляем сообщение пользователю с описанием ошибки.
        await message.reply(f"Ошибка: {str(e)}")

        # Прерываем выполнение функции, так как произошла ошибка.
        return

        # Проверяем, существует ли файл `voice_message.wav` после конвертации.
    if not os.path.exists('voice_message.wav'):
        # Формируем сообщение об ошибке, если файл не найден.
        error_msg = "Ошибка при конвертации аудиофайла. Файл отсутствует."

        # Логируем ошибку.
        logger.error(error_msg)

        # Отправляем сообщение пользователю с описанием ошибки.
        await message.reply(error_msg)

        # Прерываем выполнение функции, так как файл отсутствует.
        return

    # Распознавание текста с помощью Vosk
    with wave.open('voice_message.wav', 'rb') as wf:
        # Открываем сконвертированный аудиофайл `voice_message.wav` для чтения.

        # Создаём объект `KaldiRecognizer` для распознавания речи с использованием модели Vosk.
        rec = KaldiRecognizer(model, wf.getframerate())

        while True:
            # Читаем очередную порцию аудиоданных из файла.
            data = wf.readframes(4000)

            if len(data) == 0:
                # Если данных больше нет, выходим из цикла.
                break

                # Пытаемся распознать текущую порцию аудиоданных.
            if rec.AcceptWaveform(data):

                # Получаем промежуточный результат распознавания в виде строки JSON.
                result = rec.Result()

                # Парсим JSON-строку в словарь.
                result_dict = json.loads(result)

                # Извлекаем текст из словаря, если он есть.
                text = result_dict.get('text', '')

                # Проверяем, есть ли распознанный текст.
                if text:
                    # Логируем промежуточный результат распознавания.
                    logger.info(f"Распознанный текст (частично): {text}")

                    # Отправляем распознанный текст пользователю.
                    await message.reply(text)

        # Получаем финальный результат распознавания, после окончания чтения файла.
        final_result = rec.FinalResult()

        # Парсим JSON-строку в словарь.
        final_result_dict = json.loads(final_result)

        # Извлекаем финальный распознанный текст.
        final_text = final_result_dict.get('text', '')

        # Проверяем, есть ли финальный текст.
        if final_text:
            # Логируем финальный результат распознавания.
            logger.info(f"Распознанный текст (окончательно): {final_text}")

            # Отправляем финальный текст пользователю.
            await message.reply(final_text)


async def main():
    """
    Главная функция запуска бота. Удаляет старые файлы и начинает процесс polling.
    """
    logger.info("Запуск бота...")
    # Удаление старых аудиофайлов
    for file_path in glob.glob("*.ogg") + glob.glob("*.wav"):
        try:
            os.remove(file_path)
            logger.info(f"Удалён файл: {file_path}")
        except Exception as e:
            logger.warning(f"Не удалось удалить файл {file_path}: {e}")

    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.error("Bot stopped!")
