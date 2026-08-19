import asyncio

from dotenv import load_dotenv
from google import genai

from synthesis import generate_blueprint


SMOKE_PROFILE: dict[str, object] = {
    "experience_level": "CS student",
    "preferred_languages": ["Python"],
    "preferred_frameworks": ["FastAPI"],
    "learning_style": "step-by-step",
    "response_detail": "detailed",
    "accessibility_preferences": ["clear headings"],
}
SMOKE_SOURCE_TEXT = (
    "Design a small command-line study planner that lets a student create "
    "assignments, set deadlines, and view the next three tasks."
)


async def main() -> None:
    """Run one live structured-generation request and print the result."""
    load_dotenv()
    client = genai.Client()
    try:
        blueprint = await generate_blueprint(
            client,
            SMOKE_PROFILE,
            [],
            SMOKE_SOURCE_TEXT,
        )
        print(blueprint.model_dump_json(indent=2))
    finally:
        try:
            await client.aio.aclose()
        finally:
            client.close()


if __name__ == "__main__":
    asyncio.run(main())
