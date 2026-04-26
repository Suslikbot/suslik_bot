import logging
from asyncio import sleep
from base64 import b64encode
from http import HTTPStatus

import openai
from aiogram.types import Message
from openai import AsyncOpenAI, BadRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User

logger = logging.getLogger(__name__)




class AIClient:
    def __init__(
            self,
            token: str,
            model: str,
            system_prompt: str | None = None,
            vector_store_id: str | None = None,
    ):
        self.client = AsyncOpenAI(api_key=token)
        self._responses_api = getattr(self.client, "responses", None)
        self.model = model
        self.system_prompt = system_prompt
        self.vector_store_id = vector_store_id

    def _get_responses_api(self):
        if self._responses_api is None:
            raise RuntimeError(
                "Installed openai client does not expose AsyncOpenAI.responses. "
                "Please upgrade openai package to a version with Responses API support. "
                f"Current version: {openai.__version__}."
            )
        return self._responses_api

    def _build_response_options(self) -> dict[str, object]:
        options: dict[str, object] = {}
        if self.system_prompt:
            options["instructions"] = self.system_prompt
        if self.vector_store_id:
            options["tools"] = [
                {
                    "type": "file_search",
                    "vector_store_ids": [self.vector_store_id],
                }
            ]
        return options

    async def delete_thread(self, response_id: str):
        if not response_id.startswith("resp_"):
            return
        responses_api = self._get_responses_api()
        await responses_api.delete(response_id)

    @staticmethod
    def _normalize_previous_response_id(response_id: str | None) -> str | None:
        if response_id and response_id.startswith("resp_"):
            return response_id
        if response_id:
            logger.info("Skipping non-responses chain id: %s", response_id)
        return None

    async def _ensure_thread_available(self, _response_id: str | None, _message: Message, _fullname: str):
            """Responses API is stateless per request and does not expose run polling."""


    async def _safe_create_message( # noqa: PLR0913
        self,
        response_id: str | None,
        content: str | list[dict[str, object]],
        message: Message,
        fullname: str,
        retry: int = 0,
        max_retries: int = 3,
    ) -> str | None:
        previous_response_id = self._normalize_previous_response_id(response_id)
        responses_api = self._get_responses_api()
        try:
            logger.info(
                "external api request",
                extra={
                    "provider": "openai",
                    "operation": "responses.create",
                    "has_previous_response_id": bool(previous_response_id),
                },
            )
            response = await responses_api.create(
                model=self.model,
                input=[{"role": "user", "content": content}],
                previous_response_id=previous_response_id,
                **self._build_response_options(),
            )
            logger.info(
                "external api response",
                extra={"provider": "openai", "operation": "responses.create", "response_id": response.id},
            )

        except BadRequestError as e:
            if "previous_response_id" in str(e):
                logger.warning("Invalid response chain (retry=%s)", retry)
                if retry >= max_retries:
                    await message.answer("Произошла ошибка: ассистент сейчас занят, попробуйте позже.")
                    return None
                await sleep(2)
                return await self._safe_create_message(None, content, message, fullname, retry + 1, max_retries)
            raise
        return response.id

    def _extract_latest_text_response(self, messages) -> str | None:
        for message in messages.data:
            if message.role != "assistant":
                continue
            for content in message.content:
                text = getattr(content, "text", None)
                if text and text.value:
                    return text.value
        return None

    async def _run_thread_and_get_response(self, response_id: str) -> tuple[str | None, str]:
        responses_api = self._get_responses_api()
        logger.info(
            "external api request",
            extra={"provider": "openai", "operation": "responses.retrieve", "response_id": response_id},
        )
        response = await responses_api.retrieve(response_id)
        logger.info(
            "external api response",
            extra={"provider": "openai", "operation": "responses.retrieve", "response_id": response.id},
        )
        text_response = response.output_text
        if text_response:
            logger.debug(f"Response {response_id} returned: {text_response[:100]}...")
        return text_response, response.id


    async def get_response( # noqa: PLR0913
        self,
        ai_thread_id: str | None,
        text: str,
        message: Message,
        fullname: str,
        retry: int = 0,
        max_retries: int = 3,
    ) -> tuple[str | None, str | None]:
        response_id = await self._safe_create_message(ai_thread_id, text, message, fullname, retry, max_retries)
        if not response_id:
            return None, ai_thread_id

        response_text, new_response_id = await self._run_thread_and_get_response(response_id)
        return response_text, new_response_id

    async def get_response_with_image( # noqa: PLR0913
        self,
        thread_id: str | None,
        text: str,
        image_bytes: bytes,
        message: Message,
        fullname: str,
        retry: int = 0,
        max_retries: int = 3,
    ) -> tuple[str | None, str | None]:
        try:
            await self._ensure_thread_available(thread_id, message, fullname)
            content = [
                {"type": "input_text", "text": text},
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{b64encode(image_bytes).decode('ascii')}",
                },
            ]

            response_id = await self._safe_create_message(thread_id, content, message, fullname, retry, max_retries)
            if not response_id:
                return None, thread_id

            response_text, new_response_id = await self._run_thread_and_get_response(response_id)

        except BadRequestError as e:
            logger.exception("OpenAI API Error")
            if e.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                return "Превышены лимиты запросов. Пожалуйста, попробуйте позже.", thread_id
            return "Ошибка при обработке изображения. Убедитесь, что файл корректного формата.", thread_id
        else:
            return response_text, new_response_id


    async def apply_context_to_thread(
        self,
        user: User,
        context: str,
        db_session: AsyncSession,
        *,
        use_existing_thread: bool = False,
    ) -> str:
        responses_api = self._get_responses_api()
        logger.info(
            "external api request",
            extra={
                "provider": "openai",
                "operation": "responses.create",
                "apply_context": True,
                "use_existing_thread": use_existing_thread,
            },
        )
        response = await responses_api.create(
            model=self.model,
            input=[{"role": "user", "content": context}],
            previous_response_id=self._normalize_previous_response_id(user.ai_thread) if use_existing_thread else None,
            **self._build_response_options(),
        )
        logger.info(
            "external api response",
            extra={"provider": "openai", "operation": "responses.create", "response_id": response.id},
        )
        thread_id = response.id
        user.ai_thread = thread_id
        user.is_context_added = True
        db_session.add(user)
        await db_session.flush()
        logger.info("Added context to thread %s", thread_id)
        return thread_id
