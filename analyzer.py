from __future__ import annotations
"""
Core AI-processing logic for Problem Radar.

This module is intentionally free of any *required* paid API dependency.
The core artifact it produces is a PROMPT (a plain string), and the core
thing it consumes to produce results is a RESPONSE (a plain string of JSON
text). How that prompt gets turned into a response is up to you:

  - MANUAL / FREE: paste build_full_prompt(posts) into your preferred LLM,
    then paste the reply into parse_response().
    This is the default workflow for this proof of concept.

  - AUTOMATED: call analyze_posts_via_api(posts), which uses Groq GPT-OSS 120B
    first and falls back to GPT-OSS 20B on temporary failures. Gemini remains
    available as a direct selection. Provider SDKs are imported only when
    called, so the manual workflow remains dependency-free.

Either way, the public contract later stages of the project should depend
on is the same: give it `list[Post]`, get back `list[Problem]`.
"""

import json
import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from models import Post, Problem

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_FALLBACK_MODEL = "openai/gpt-oss-20b"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_MODEL = GROQ_MODEL
DEFAULT_PROBLEM_KEYWORDS = ["wish", "track", "annoying", "alternative", "recommend", "frustrating", "hate"]
MAX_POST_BODY_CHARS = 1_500
MAX_TOTAL_POST_BODY_CHARS = 60_000
GROQ_MAX_POST_BODY_CHARS = 800
GROQ_MAX_TOTAL_POST_BODY_CHARS = 8_000
MAX_ANALYSIS_POSTS = 25
GROQ_MAX_COMPLETION_TOKENS = 1_600
GROQ_DEFAULT_COOLDOWN_SECONDS = 60
GROQ_COOLDOWN_UNTIL: dict[str, float] = {}
GROQ_COOLDOWN_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisResult:
    problems: list[Problem]
    provider: str
    model: str
    fallback_used: bool = False


class GroqRequestError(RuntimeError):
    """A sanitized Groq failure with enough detail to decide on fallback."""

    def __init__(
        self,
        message: str,
        retryable: bool,
        retry_after_seconds: int | None = None,
    ):
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class ProviderUnavailableError(RuntimeError):
    """Raised when the selected provider and its fallback cannot complete."""


def _retry_after_seconds(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or getattr(error, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
        return max(1, math.ceil(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def _start_groq_cooldown(
    model: str,
    seconds: int,
    now: float | None = None,
) -> None:
    current_time = time.monotonic() if now is None else now
    with GROQ_COOLDOWN_LOCK:
        GROQ_COOLDOWN_UNTIL[model] = max(
            GROQ_COOLDOWN_UNTIL.get(model, 0.0),
            current_time + max(1, seconds),
        )


def _groq_cooldown_remaining(model: str, now: float | None = None) -> int:
    current_time = time.monotonic() if now is None else now
    with GROQ_COOLDOWN_LOCK:
        cooldown_until = GROQ_COOLDOWN_UNTIL.get(model, 0.0)
        if cooldown_until <= current_time:
            GROQ_COOLDOWN_UNTIL.pop(model, None)
            return 0
        return max(1, math.ceil(cooldown_until - current_time))


def _remember_groq_failure(model: str, error: GroqRequestError) -> None:
    if error.retry_after_seconds:
        _start_groq_cooldown(model, error.retry_after_seconds)


SYSTEM_PROMPT = """You are an analyst for "Problem Radar", a tool that reads online \
discussion posts (Reddit threads, app reviews, forum posts) and finds RECURRING \
problems, frustrations, unmet needs, or inefficient workarounds that could plausibly \
be solved with a piece of software.

You will be given a numbered list of posts, each with a short id like [p1].

Your job:
1. Read all posts and identify clusters of posts that describe the SAME underlying \
problem — not just posts that share a topic, subreddit, or a few keywords.
2. Do NOT force posts into a shared category just because they are thematically \
adjacent. Two posts about "money" or "cooking" are not automatically the same \
problem. Only group posts if a reasonable person would say "these people are \
describing the same frustration and would want the same solution."
3. A single post describing a one-off, unrelated complaint should NOT be included \
in any cluster and should NOT be reported as a problem. Only report problems that \
recur across MULTIPLE posts (2 or more) unless the instructions say otherwise.
4. It is completely fine, and expected, for some posts to not belong to any \
recurring problem. Do not invent a category just to use every post.
5. Be conservative: if you are unsure whether two posts describe the same problem, \
treat them as different problems rather than merging them.
6. Prioritize problems where software can create a meaningful improvement. Do not
discard a genuinely recurring cluster merely because people or processes are also
part of the resolution. Only exclude a problem when there is no credible software
role at all. Do not invent a generic dashboard, reminder, or directory to force a
software fit; instead, keep the opportunity score modest when software fit is weak.

For each genuinely recurring problem you find, produce an object with these exact \
fields:
  - "title": short, specific problem title (not a generic category name)
  - "description": one concise sentence clearly describing the problem
  - "post_count": integer, number of posts in the input describing this problem
  - "representative_post_ids": list of the post ids (e.g. ["p1", "p3"]) that best \
represent this problem — include ALL posts you assigned to this cluster
  - "who_experiences": short description of who experiences this problem
  - "existing_workarounds": one concise sentence about the workarounds people currently use, based on the posts
  - "potential_solution": one concise sentence describing a specific, plausible
software product that addresses the core problem. State the user, the product's key
workflow, and how it improves on the current workaround. Do not repeat an existing
non-software workaround.
  - "pain_level": integer 1-10, how painful/frustrating this problem seems based on \
the language used in the posts
  - "opportunity_score": integer 1-100, your estimate of how promising this is as a \
software opportunity, considering recurrence, pain level, and whether existing \
workarounds are clearly inadequate
  - "score_reasoning": one concise sentence explaining the opportunity_score

Return no more than 3 objects, ordered from strongest to weakest opportunity. \
Respond with ONLY a JSON array of these objects. No markdown code fences, no \
preamble, no commentary, no trailing text. If you find zero recurring problems, \
respond with an empty JSON array: []
"""


def _build_user_prompt(
    posts: list[Post],
    max_post_body_chars: int | None = None,
    max_total_body_chars: int | None = None,
) -> str:
    per_post_limit = MAX_POST_BODY_CHARS if max_post_body_chars is None else max_post_body_chars
    total_limit = MAX_TOTAL_POST_BODY_CHARS if max_total_body_chars is None else max_total_body_chars
    remaining_body_chars = total_limit
    posts_text_parts = []
    for index, post in enumerate(posts):
        remaining_posts = len(posts) - index
        body_limit = min(
            per_post_limit,
            remaining_body_chars // remaining_posts,
        )
        posts_text_parts.append(post.as_prompt_text(body_limit=body_limit))
        remaining_body_chars -= min(len(post.body), body_limit)

    posts_text = "\n\n".join(posts_text_parts)
    return (
        f"Here are {len(posts)} posts to analyze:\n\n"
        f"{posts_text}\n\n"
        "Identify the genuinely recurring problems as instructed and return the JSON array."
    )


def build_full_prompt(posts: list[Post]) -> str:
    """
    Build a single, self-contained prompt combining the system instructions
    and the posts. Designed to be copy-pasted as ONE message into a chat
    interface, which may not expose a separate system-prompt field.
    """
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "---\n\n"
        f"{_build_user_prompt(posts)}"
    )


def parse_response(raw_text: str) -> list[Problem]:
    """
    Parse a model's JSON output (whether it came from the API or was
    pasted in manually from an LLM) into Problem objects. Tolerates
    stray whitespace and accidental code-fence wrapping.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    # Gemini occasionally escapes field-name underscores despite JSON mode.
    # ``\_`` is not a valid JSON escape sequence, so normalize this harmless
    # formatting artifact before parsing the otherwise-valid response.
    text = text.replace("\\_", "_")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            "Could not parse the response as JSON. Make sure you pasted the "
            "model's FULL reply and nothing else (no extra commentary before "
            "or after the JSON array).\n\n"
            f"Raw text received:\n{raw_text}"
        ) from e

    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError("The model response must be a JSON array of problem objects.")

    problems = []
    for item in data:
        problems.append(
            Problem(
                title=item.get("title", "Untitled problem"),
                description=item.get("description", ""),
                post_count=item.get("post_count", len(item.get("representative_post_ids", []))),
                representative_post_ids=item.get("representative_post_ids", []),
                who_experiences=item.get("who_experiences", ""),
                existing_workarounds=item.get("existing_workarounds", ""),
                potential_solution=item.get("potential_solution", ""),
                pain_level=item.get("pain_level", 0),
                opportunity_score=item.get("opportunity_score", 0),
                score_reasoning=item.get("score_reasoning", ""),
            )
        )
    return problems


def expand_topic_keywords_via_api(
    topic: str,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    on_fallback: Callable[[str, str], None] | None = None,
) -> list[str]:
    import os

    prompt = (
        f"For this topic, return exactly 3 short terms people are likely to use in "
        f"Reddit posts when describing a frustrating, repeated problem that software "
        f"could plausibly improve. Favor pain, friction, failed workarounds, or unmet "
        f"software needs—not broad topic categories or app features. Each term must be "
        f"one or two words and likely to appear in a post title or body.\n\n"
        f"Topic: '{topic}'\n"
        f"Return ONLY a JSON array of 3 strings."
    )

    def sanitize(raw_text: str) -> list[str]:
        keywords = json.loads(raw_text)
        if not isinstance(keywords, list):
            return []
        return [
            keyword.strip()
            for keyword in keywords
            if isinstance(keyword, str) and keyword.strip() and len(keyword.split()) <= 2
        ][:3]

    if model == GROQ_MODEL:
        groq_key = api_key or os.environ.get("GROQ_API_KEY")
        if not groq_key:
            logger.warning("Groq keyword generation skipped because GROQ_API_KEY is not set")
            return DEFAULT_PROBLEM_KEYWORDS

        for index, groq_model in enumerate((GROQ_MODEL, GROQ_FALLBACK_MODEL)):
            if index == 1 and on_fallback:
                on_fallback(GROQ_MODEL, GROQ_FALLBACK_MODEL)
            cooldown_remaining = _groq_cooldown_remaining(groq_model)
            if cooldown_remaining:
                logger.warning(
                    "%s keyword generation is cooling down for %s seconds",
                    groq_model,
                    cooldown_remaining,
                )
                continue
            try:
                keywords = sanitize(
                    _generate_groq_text(
                        prompt,
                        model=groq_model,
                        api_key=groq_key,
                        max_tokens=200,
                    )
                )
                if keywords:
                    return keywords
                error = GroqRequestError(
                    f"{groq_model} returned no usable Smart signals.",
                    retryable=True,
                )
            except (ValueError, json.JSONDecodeError):
                error = GroqRequestError(
                    f"{groq_model} returned invalid Smart signal JSON.",
                    retryable=True,
                )
            except GroqRequestError as request_error:
                error = request_error
            logger.warning("%s keyword generation failed: %s", groq_model, error)
            if not error.retryable:
                break
            _remember_groq_failure(groq_model, error)
        return DEFAULT_PROBLEM_KEYWORDS

    gemini_key = api_key or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            keywords = sanitize(
                _generate_gemini_text(prompt, model=model, api_key=gemini_key)
            )
            if keywords:
                return keywords
        except Exception as error:
            logger.warning("Gemini keyword generation failed; using built-in signals: %s", error)
    return DEFAULT_PROBLEM_KEYWORDS


def _generate_groq_text(
    prompt: str,
    model: str,
    api_key: str,
    max_tokens: int,
    system_instruction: str | None = None,
) -> str:
    try:
        from groq import Groq
    except ImportError as error:
        raise GroqRequestError(
            "Groq support requires the `groq` package. Run `pip install -r requirements.txt`.",
            retryable=False,
        ) from error

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    try:
        response = Groq(api_key=api_key).chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_completion_tokens=max_tokens,
            reasoning_effort="low",
        )
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        error_name = type(error).__name__.casefold()
        message = str(error).casefold()
        retryable = (
            status_code == 429
            or isinstance(status_code, int) and status_code >= 500
            or "ratelimit" in error_name
            or "timeout" in error_name
            or "connection" in error_name
            or "rate limit" in message
            or "429" in message
            or "503" in message
            or "timed out" in message
            or "temporarily unavailable" in message
        )
        raise GroqRequestError(
            f"Groq API request failed ({status_code or 'connection error'}).",
            retryable=retryable,
            retry_after_seconds=(
                _retry_after_seconds(error) or GROQ_DEFAULT_COOLDOWN_SECONDS
                if retryable
                else None
            ),
        ) from error

    try:
        raw_text = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
    except (AttributeError, IndexError, TypeError) as error:
        raise GroqRequestError("Groq returned an unexpected response.", retryable=True) from error

    if not raw_text or not raw_text.strip():
        raise GroqRequestError("Groq returned no text response.", retryable=True)
    if str(finish_reason).casefold() == "length":
        raise GroqRequestError("Groq's response reached its output limit.", retryable=True)
    return raw_text


def _generate_gemini_text(
    prompt: str,
    model: str,
    api_key: str,
    max_tokens: int | None = None,
    system_instruction: str | None = None,
) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise RuntimeError(
            "Gemini support requires the `google-genai` package. "
            "Run `pip install -r requirements.txt`."
        ) from error

    config_args = {
        "response_mime_type": "application/json",
        "temperature": 0.2,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }
    if max_tokens is not None:
        config_args["max_output_tokens"] = max_tokens
    if system_instruction:
        config_args["system_instruction"] = system_instruction

    try:
        response = genai.Client(api_key=api_key).models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_args),
        )
        raw_text = response.text
    except Exception as error:
        raise RuntimeError(
            f"Gemini API request failed: {error}. Check GEMINI_API_KEY, model access, "
            "and Gemini API quota."
        ) from error

    if not raw_text or not raw_text.strip():
        raise RuntimeError("Gemini returned no text response to parse.")

    try:
        finish_reason = response.candidates[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        finish_reason = None
    finish_reason_text = str(finish_reason).upper()
    if finish_reason is not None and (
        "MAX_TOKENS" in finish_reason_text or finish_reason_text == "2"
    ):
        raise RuntimeError(
            f"Gemini's response was truncated (hit max_output_tokens={max_tokens}) "
            "before finishing the JSON array."
        )
    return raw_text


def analyze_posts_via_api_raw(
    posts: list[Post],
    model: str = DEFAULT_GEMINI_MODEL,
    api_key: Optional[str] = None,
    max_tokens: int = 8000,
) -> str:
    """
    Automated path: send `posts` to Gemini and return the RAW response text
    (unparsed JSON string), after checking for truncation. Split out from
    analyze_posts_via_api() so callers that need the raw model output can
    handle it before or independently of parsing it.
    """
    import os

    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Create a Gemini API key in Google AI Studio "
            "and set it before running `python main.py run`."
        )

    return _generate_gemini_text(
        _build_user_prompt(posts),
        model=model,
        api_key=resolved_api_key,
        max_tokens=max_tokens,
        system_instruction=SYSTEM_PROMPT,
    )


def _analyze_groq(
    posts: list[Post],
    model: str = GROQ_MODEL,
    api_key: str | None = None,
) -> list[Problem]:
    import os

    resolved_api_key = api_key or os.environ.get("GROQ_API_KEY")
    if not resolved_api_key:
        raise GroqRequestError("GROQ_API_KEY is not set.", retryable=False)
    raw_text = _generate_groq_text(
        _build_user_prompt(
            posts[:MAX_ANALYSIS_POSTS],
            max_post_body_chars=GROQ_MAX_POST_BODY_CHARS,
            max_total_body_chars=GROQ_MAX_TOTAL_POST_BODY_CHARS,
        ),
        model=model,
        api_key=resolved_api_key,
        max_tokens=GROQ_MAX_COMPLETION_TOKENS,
        system_instruction=SYSTEM_PROMPT,
    )
    try:
        return parse_response(raw_text)
    except ValueError as error:
        raise GroqRequestError("Groq returned invalid analysis JSON.", retryable=True) from error


def _analyze_gemini(
    posts: list[Post],
    model: str = DEFAULT_GEMINI_MODEL,
    api_key: str | None = None,
    max_tokens: int = 8000,
) -> list[Problem]:
    return parse_response(
        analyze_posts_via_api_raw(
            posts[:MAX_ANALYSIS_POSTS],
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
        )
    )


def analyze_posts_with_metadata(
    posts: list[Post],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    max_tokens: int = 8000,
    on_fallback: Callable[[str, str], None] | None = None,
) -> AnalysisResult:
    """Analyze with the selected route and report the provider that succeeded."""
    if model != GROQ_MODEL:
        return AnalysisResult(
            problems=_analyze_gemini(posts, model=model, api_key=api_key, max_tokens=max_tokens),
            provider="gemini",
            model=model,
        )

    last_error = None
    for index, groq_model in enumerate((GROQ_MODEL, GROQ_FALLBACK_MODEL)):
        if index == 1 and on_fallback:
            on_fallback(GROQ_MODEL, GROQ_FALLBACK_MODEL)
        cooldown_remaining = _groq_cooldown_remaining(groq_model)
        if cooldown_remaining:
            last_error = GroqRequestError(
                f"{groq_model} is cooling down for {cooldown_remaining} seconds.",
                retryable=True,
            )
            continue
        try:
            return AnalysisResult(
                problems=_analyze_groq(posts, model=groq_model, api_key=api_key),
                provider="groq",
                model=groq_model,
                fallback_used=index == 1,
            )
        except GroqRequestError as groq_error:
            if not groq_error.retryable:
                raise
            last_error = groq_error
            _remember_groq_failure(groq_model, groq_error)
            logger.warning("%s analysis unavailable: %s", groq_model, groq_error)

    raise ProviderUnavailableError(
        "Groq GPT-OSS 120B and GPT-OSS 20B could not complete the analysis."
    ) from last_error


def analyze_posts_via_api(
    posts: list[Post],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    max_tokens: int = 8000,
) -> list[Problem]:
    """
    Automated path: use the selected provider route and return Problem objects.
    The default route uses Groq GPT-OSS 120B first and GPT-OSS 20B as fallback.
    """
    return analyze_posts_with_metadata(
        posts, model=model, api_key=api_key, max_tokens=max_tokens
    ).problems
