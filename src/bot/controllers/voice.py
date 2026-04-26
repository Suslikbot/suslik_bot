import asyncio
import logging
from io import BytesIO

from aiogram.types import Message

from bot.ai_client import AIClient


async def convert_to_mp3(audio: bytes) -> bytes:
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i",
            "pipe:0",
            "-f",
            "mp3",
            "-acodec",
            "libmp3lame",
            "-b:a",
            "128k",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(input=audio)
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {stderr.decode()}")
    except FileNotFoundError as err:
        logging.exception("FFmpeg is not installed or not found in PATH.")
        raise RuntimeError("FFmpeg is not installed or not found in PATH.") from err
    else:
        return stdout


async def process_voice(message: Message, openai_client: AIClient) -> str | None:
    try:
        voice = message.voice
        file_info = await message.bot.get_file(voice.file_id)
        audio_bytes = await message.bot.download_file(file_info.file_path)
        audio_data = audio_bytes.read()

        mp3_audio = await convert_to_mp3(audio_data)
        audio_stream = BytesIO(mp3_audio)
        audio_stream.name = "audio.mp3"

        transcription_response = await openai_client.client.audio.transcriptions.create(
            file=audio_stream, model="whisper-1", response_format="text", language="ru"
        )
        return transcription_response.strip()

    except Exception:
        logging.exception("Unexpected transcription error")
        await message.reply("Произошла непредвиденная ошибка при распознавании. Пожалуйста, попробуйте позже.")
        return None


async def extract_text_from_message(message: Message, openai_client: AIClient) -> str | None:
    if message.voice:
        return await process_voice(message, openai_client)
    if message.text:
        return message.text.strip()
    await message.reply("Пожалуйста, ответьте текстом или голосовым сообщением.")
    return None
