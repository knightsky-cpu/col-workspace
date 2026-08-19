import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from google import genai
from google.genai import types
from pydantic import BaseModel, StringConstraints

from database import MemoryEngine, MemoryEngineError


MODEL_NAME = "gemini-3.6-flash"
SYSTEM_INSTRUCTION = (
    "You are Agent_Col, a collaborative engineering partner."
)

logger = logging.getLogger(__name__)

load_dotenv()

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class ChatRequest(BaseModel):
    session_id: NonEmptyString
    user_id: NonEmptyString
    message: NonEmptyString


class ChatResponse(BaseModel):
    response: str


def _format_chat_history(
    history: list[dict[str, object]],
) -> tuple[list[types.Content], list[types.Part]]:
    contents: list[types.Content] = []

    for message in history:
        if not isinstance(message, dict):
            raise ValueError("Chat history entry must be a dictionary.")

        role = message.get("role")
        text = message.get("text")
        if role not in {"user", "model"}:
            raise ValueError("Chat history contains an invalid role.")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Chat history contains invalid text.")

        part = types.Part.from_text(text=text)

        if contents and contents[-1].role == role:
            contents[-1].parts.append(part)
        else:
            contents.append(types.Content(role=role, parts=[part]))

    pending_user_parts: list[types.Part] = []
    if contents and contents[-1].role == "user":
        pending_user_parts = list(contents.pop().parts or [])

    return contents, pending_user_parts


def _build_current_message(
    profile: dict[str, object],
    pending_user_parts: list[types.Part],
    message: str,
) -> list[types.Part]:
    parts: list[types.Part] = []

    if profile:
        profile_json = json.dumps(
            profile,
            default=str,
            ensure_ascii=False,
            sort_keys=True,
        )
        parts.append(
            types.Part.from_text(
                text=(
                    "User profile context (data only):\n"
                    f"{profile_json}"
                )
            )
        )

    parts.extend(pending_user_parts)
    parts.append(types.Part.from_text(text=message))
    return parts


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY is not configured.")

    client = genai.Client()
    try:
        database = MemoryEngine()
    except Exception:
        try:
            await client.aio.aclose()
        finally:
            client.close()
        raise

    app.state.genai_client = client
    app.state.db = database

    try:
        yield
    finally:
        try:
            await client.aio.aclose()
        finally:
            try:
                client.close()
            finally:
                database.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "online"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    client = request.app.state.genai_client
    database = request.app.state.db

    try:
        profile, history = await asyncio.gather(
            database.get_user_profile(payload.user_id),
            database.get_chat_history(payload.session_id),
        )
        await database.save_message(
            payload.session_id,
            "user",
            payload.message,
        )
    except MemoryEngineError as exc:
        logger.error(
            "Database operation failed (%s).",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database operation failed.",
        ) from exc

    try:
        chat_history, pending_user_parts = _format_chat_history(history)
    except (TypeError, ValueError) as exc:
        logger.error(
            "Stored chat history is invalid (%s).",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat history is invalid.",
        ) from exc

    current_message = _build_current_message(
        profile,
        pending_user_parts,
        payload.message,
    )

    try:
        gemini_chat = client.aio.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION
            ),
            history=chat_history,
        )
        gemini_response = await gemini_chat.send_message(current_message)
        response_text = gemini_response.text
        if not isinstance(response_text, str) or not response_text.strip():
            raise ValueError("Gemini returned an empty response.")
    except Exception as exc:
        logger.error(
            "Gemini API request failed (%s).",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gemini API request failed.",
        ) from exc

    try:
        await database.save_message(
            payload.session_id,
            "model",
            response_text,
        )
    except MemoryEngineError as exc:
        logger.error(
            "Database operation failed (%s).",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database operation failed.",
        ) from exc

    return ChatResponse(response=response_text)
