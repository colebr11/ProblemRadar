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

  - AUTOMATED: call analyze_posts_via_api(posts), which uses the Gemini API
    and requires GEMINI_API_KEY. The Gemini SDK is imported only when this
    function is called, so the manual workflow remains dependency-free.

Either way, the public contract later stages of the project should depend
on is the same: give it `list[Post]`, get back `list[Problem]`.
"""

import json
from typing import Optional

from models import Post, Problem

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_PROBLEM_KEYWORDS = ["wish", "track", "annoying", "alternative", "recommend", "frustrating", "hate"]

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
  - "description": 1-2 sentences clearly describing the problem
  - "post_count": integer, number of posts in the input describing this problem
  - "representative_post_ids": list of the post ids (e.g. ["p1", "p3"]) that best \
represent this problem — include ALL posts you assigned to this cluster
  - "who_experiences": short description of who experiences this problem
  - "existing_workarounds": what workarounds people currently use, based on the posts
  - "potential_solution": a specific, plausible software product that addresses the
core problem. State the user, the product's key workflow, and how it improves on the
current workaround. Do not repeat an existing non-software workaround.
  - "pain_level": integer 1-10, how painful/frustrating this problem seems based on \
the language used in the posts
  - "opportunity_score": integer 1-100, your estimate of how promising this is as a \
software opportunity, considering recurrence, pain level, and whether existing \
workarounds are clearly inadequate
  - "score_reasoning": 1-3 sentences explaining the opportunity_score

Return no more than 5 objects, ordered from strongest to weakest opportunity. \
Respond with ONLY a JSON array of these objects. No markdown code fences, no \
preamble, no commentary, no trailing text. If you find zero recurring problems, \
respond with an empty JSON array: []
"""


def _build_user_prompt(posts: list[Post]) -> str:
    posts_text = "\n\n".join(p.as_prompt_text() for p in posts)
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


def expand_topic_keywords_via_api(topic: str, api_key: str | None = None) -> list[str]:
    import os

    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        return DEFAULT_PROBLEM_KEYWORDS

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=resolved_api_key)

        # Enforce short single words or 2-word pain signals (no full phrases)
        prompt = (
            f"For this topic, return exactly 3 short terms people are likely to use in "
            f"Reddit posts when describing a frustrating, repeated problem that software "
            f"could plausibly improve. Favor pain, friction, failed workarounds, or unmet "
            f"software needs—not broad topic categories or app features. Each term must be "
            f"one or two words and likely to appear in a post title or body.\n\n"
            f"Topic: '{topic}'\n"
            f"Return ONLY a JSON array of 3 strings."
        )

        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)
            )
        )
        keywords = json.loads(response.text)
        # Sanitizer: strip long phrases to protect Reddit search
        sanitized = [k.strip() for k in keywords if len(k.split()) <= 2]
        return sanitized if sanitized else DEFAULT_PROBLEM_KEYWORDS
    except Exception as e:
        print(f"Error generating keywords: {e}")
        return DEFAULT_PROBLEM_KEYWORDS


def analyze_posts_via_api_raw(
    posts: list[Post],
    model: str = DEFAULT_MODEL,
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

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "Gemini support requires the `google-genai` package. "
            "Run `pip install -r requirements.txt`."
        ) from e

    client = genai.Client(api_key=resolved_api_key)
    try:
        response = client.models.generate_content(
            model=model,
            contents=_build_user_prompt(posts),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            ),
        )
        raw_text = response.text
    except Exception as e:
        raise RuntimeError(
            f"Gemini API request failed: {e}. Check GEMINI_API_KEY, model access, "
            "and Gemini API quota."
        ) from e

    if not raw_text or not raw_text.strip():
        raise RuntimeError("Gemini returned no text response to parse.")

    # Detect truncation BEFORE attempting to parse. If Gemini hit the
    # max_output_tokens cap mid-generation, response.text will contain a
    # syntactically incomplete JSON array (e.g. a dangling, unterminated
    # string). Rather than let that surface as a confusing JSONDecodeError
    # deep inside parse_response, check finish_reason and fail fast with an
    # actionable message.
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
            "before finishing the JSON array. Increase max_tokens (e.g. "
            "analyze_posts_via_api(posts, max_tokens=12000)) or reduce the number "
            "of posts analyzed."
        )

    return raw_text


def analyze_posts_via_api(
    posts: list[Post],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    max_tokens: int = 8000,
) -> list[Problem]:
    """
    Automated path: send `posts` to Gemini and return Problem objects
    directly. Requires `google-genai` and GEMINI_API_KEY; it is not needed
    for the manual workflow (see build_full_prompt / parse_response above).
    Thin wrapper around analyze_posts_via_api_raw() + parse_response() for
    callers that just want the parsed result and don't need the raw text.
    """
    raw_text = analyze_posts_via_api_raw(
        posts, model=model, api_key=api_key, max_tokens=max_tokens
    )
    return parse_response(raw_text)
