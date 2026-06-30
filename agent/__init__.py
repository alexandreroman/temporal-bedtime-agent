from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from agent.config import PYDANTIC_AI_MODEL
from agent.conversation import AgentInput, Conversation, Message
from agent.prompt import SYSTEM_PROMPT

__all__ = [
    "AgentInput",
    "Conversation",
    "Message",
    "SYSTEM_PROMPT",
    "StoryResponse",
    "story_agent",
]


class StoryResponse(BaseModel):
    """Agent response with progressive story elements.

    Field order matters: structured-output models (both OpenAI and
    Anthropic) emit JSON in declared order, which lets us force the
    model to commit to two key decisions before it writes any prose.
    `language` is declared FIRST to lock the user's current language;
    without this, the model anchors on its own previous reply's
    language and ignores mid-conversation switches. `writing_story` is
    declared SECOND, as an explicit boolean the model must commit to
    BEFORE writing any prose: it forces a single approve/not-approve
    decision up front, so `story_text` and `message` below stay
    consistent with it. `story_text` is declared THIRD so that on the
    post-recap turn the model has already decided whether the user
    approved (writing_story=true: fill the 3-paragraph story) or not
    (writing_story=false: leave empty); without this commit-first
    ordering, the model writes a "story is ready" acknowledgement in
    `message` and then drops `story_text` to its "" default — a "dry
    run" with no actual story, which strands the user in a loop.
    """

    language: str = Field(
        default="English",
        description=(
            "The English name of the language the user wrote in for "
            "their MOST RECENT SUBSTANTIVE reply (e.g. 'French', "
            "'Spanish', 'English', 'German', 'Italian'). 'Substantive' "
            "means the reply has enough lexical content to identify a "
            "language — a phrase or sentence. If the latest user reply "
            "is a bare affirmative ('ok', 'oui', 'yes', '👍'), an emoji, "
            "or an isolated proper noun, that reply is NOT substantive: "
            "carry the language forward from the previous substantive "
            "user message instead of resetting to 'English' or to your "
            "own previous reply's language. Ignore the language of "
            "your own previous replies. If the user just switched in a "
            "substantive reply, this MUST reflect their NEW language. "
            "Every other text field below MUST be written in this "
            "language. Default to 'English' on turn 1 before any user "
            "input. Used by the application to force any visible text "
            "inside the illustration to be rendered in that language."
        ),
    )
    writing_story: bool = Field(
        default=False,
        description=(
            "Your up-front decision for THIS turn: are you writing the full "
            "story now? Set True ONLY on the post-recap turn (turn 5+) when the "
            "user's latest reply is a short affirmative approving the recap — "
            "any of 'ok', 'OK', 'oui', 'yes', 'sí', 'sì', 'ja', \"d'accord\", "
            "'parfait', 'vas-y', 'allons-y', 'go', '👍', or a combination of "
            "these only. When True, `story_text` below MUST contain the "
            "complete 3-paragraph story and `message` MUST be a SINGLE warm "
            "sentence (no recap, no question). When False, `story_text` MUST be "
            "empty (\"\"). False on the gathering turns (1–4) and on post-recap "
            "turns where the user instead adds or swaps an ingredient. Setting "
            "this True while leaving `story_text` empty, or announcing in "
            "`message` that you will write the story while this is False, is a "
            "CRITICAL bug that strands the user in a loop."
        ),
    )
    story_text: str = Field(
        default="",
        description=(
            "The full bedtime story when the user has approved generation: "
            "exactly three paragraphs, written entirely in the language "
            "declared in `language`. On the post-recap turn (turn 5+), "
            "fill this WHENEVER the latest user reply is a short "
            "affirmative — any of 'ok', 'OK', 'oui', 'yes', 'sí', 'sì', "
            "'ja', \"d'accord\", 'parfait', 'vas-y', 'allons-y', 'go', "
            "'👍', or a combination of these only ('ok vas-y', 'oui "
            "parfait'). Each item is full approval; there is no weaker "
            "form of yes — 'sí' and 'ja' are explicit confirmations, not "
            "mere acknowledgements. Also fill it whenever the user "
            "otherwise asks for the story to be written. Leave EMPTY "
            "(\"\") on turns 1–4 (gathering phase) and on post-recap "
            "turns where the user adds a new ingredient or asks to swap "
            "one (Branches B/C) — those turns require a fresh recap in "
            "`message`, not a story. Producing an empty `story_text` "
            "while `message` says 'I'll write it' is a CRITICAL bug "
            "that strands the user in a loop."
        ),
    )
    message: str = Field(
        description=(
            "Your conversational reply to the user, rendered as Markdown in a chat UI. "
            "MUST be written entirely in the language declared in `language` above. "
            "Warm and engaging: 2–4 short sentences, with at least one of **bold**, "
            "*italics*, or a Markdown bullet list. On turn 5 (story delivery — "
            "i.e. when `story_text` has just been filled above) this is a SINGLE "
            "short warm sentence with no question and no story summary."
        ),
    )
    story_title: str = Field(
        default="",
        description=(
            "Working title for the story, in the language declared in "
            "`language`. Set as soon as the main character is known."
        ),
    )
    illustration_prompt: str = Field(
        default="",
        description=(
            "A description in English of an illustration for the story "
            "(style: children's book illustration, warm colors, friendly). "
            "Update progressively as you learn more elements. "
            "Prefer no visible text in the image unless it clearly adds "
            "value. Do NOT specify a language for in-image text here — the "
            "application appends that directive based on the `language` field. "
            "ALWAYS in English regardless of `language`."
        ),
    )


story_agent: Agent[None, StoryResponse] = Agent(
    model=PYDANTIC_AI_MODEL,
    system_prompt=SYSTEM_PROMPT,
    output_type=StoryResponse,
    model_settings=ModelSettings(temperature=0.7),
)
