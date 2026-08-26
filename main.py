"""
Problem Radar - proof of concept entry point.

Default workflow is FREE and MANUAL (no API key, no billing):

    1. python main.py generate
         -> writes prompt.txt containing the full prompt (instructions + posts)
    2. Open your preferred LLM chat, start a new chat, paste the entire contents
       of prompt.txt as your message, send it.
    3. Copy the model's entire reply (should be just a JSON array).
    4. Paste it into a new file, e.g. response.txt, in this folder.
    5. python main.py parse response.txt
         -> pretty-prints the recurring problems it found

Automated Gemini workflow (requires `google-genai` and GEMINI_API_KEY):

    python main.py run

The unified automated workflow (search + analyze + report in one step)
saves posts.json and prompt.txt along the way so every run stays locally
auditable:

    python main.py run "topic"
    python main.py run "topic" --subreddit=NYCapartments
    python main.py run "topic" --json
"""
from __future__ import annotations

import sys

from mock_data import MOCK_POSTS
from models import Post, Problem


def _archive_paths(query: str, archives_dir: str = "archives") -> tuple[str, str, str]:
    """
    Build timestamped, slugified archive file paths for a `run` on `query`,
    e.g. archives/study_tips_20260824_153012_posts.json. Using a fresh
    timestamped slug per run (rather than always overwriting posts.json /
    prompt.txt) means every run's raw data and prompt stay recoverable
    afterward, instead of being silently overwritten by the next run.
    """
    import os
    import re
    from datetime import datetime

    os.makedirs(archives_dir, exist_ok=True)

    slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_") or "run"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{slug}_{timestamp}"

    posts_path = os.path.join(archives_dir, f"{base}_posts.json")
    prompt_path = os.path.join(archives_dir, f"{base}_prompt.txt")
    response_path = os.path.join(archives_dir, f"{base}_response.txt")
    return posts_path, prompt_path, response_path


def print_problems(problems: list[Problem], posts_by_id: dict[str, Post]) -> None:
    if not problems:
        print("No recurring problems found in this batch of posts.")
        return

    print(f"\nFound {len(problems)} recurring problem(s)\n" + "=" * 60)

    for i, prob in enumerate(problems, start=1):
        print(f"\n[{i}] {prob.title}")
        print("-" * 60)
        print(f"Description:      {prob.description}")
        print(f"Post count:       {prob.post_count}")
        print(f"Who experiences:  {prob.who_experiences}")
        print(f"Workarounds:      {prob.existing_workarounds}")
        print(f"Pain level:       {prob.pain_level}/10")
        print(f"Opportunity score:{prob.opportunity_score}/100")
        print(f"Reasoning:        {prob.score_reasoning}")
        print("Representative posts:")
        for pid in prob.representative_post_ids:
            post = posts_by_id.get(pid)
            if post:
                snippet = post.title or post.body[:60]
                print(f"  - {pid}: {snippet}")
            else:
                print(f"  - {pid}: (id not found in input set)")


def cmd_generate(
    query: str = "tracking subscriptions",
    output_path: str = "prompt.txt",
    posts_path: str = "posts.json",
    use_signals: bool = False,
    subreddit: str | None = None,
) -> None:
    from analyzer import build_full_prompt
    from models import save_posts
    from reddit_client import search_reddit_for_problem_signals, search_reddit_posts

    if use_signals:
        target = f"r/{subreddit}" if subreddit else "all Reddit"
        print(f"Searching for problem signals around: '{query}' ({target})...")
        posts = search_reddit_for_problem_signals(query, limit=50, subreddit=subreddit)
    else:
        target = f" in r/{subreddit}" if subreddit else ""
        print(f"Searching Reddit for query: '{query}'{target}...")
        posts = search_reddit_posts(query, subreddit=subreddit)

    if not posts:
        print(f"No posts found for '{query}'. Prompt was not generated.")
        return

    save_posts(posts, posts_path)
    print(f"Saved {len(posts)} posts to '{posts_path}'.")

    prompt = build_full_prompt(posts)
    with open(output_path, "w") as f:
        f.write(prompt)

    print(f"Wrote prompt for {len(posts)} posts to '{output_path}'.\n")
    print("Next steps:")
    print("  1. Open your preferred LLM chat and start a new chat.")
    print(f"  2. Paste the entire contents of '{output_path}' as your message and send it.")
    print("  3. Copy the model's full reply (it should be just a JSON array, nothing else).")
    print("  4. Paste it into a new text file, e.g. response.txt, in this folder.")
    print("  5. Run: python main.py parse response.txt")


def cmd_parse(
    response_path: str,
    posts_path: str = "posts.json",
    as_json: bool = False,
) -> None:
    import os
    from analyzer import parse_response
    from mock_data import MOCK_POSTS
    from models import load_posts

    with open(response_path, "r") as f:
        raw_text = f.read()

    problems = parse_response(raw_text)

    # Try requested posts_path first, then auto-derive from response_path (e.g. in archives/)
    posts = load_posts(posts_path)
    if not posts:
        dirname = os.path.dirname(response_path)
        basename = os.path.basename(response_path)
        if "_response" in basename:
            alt_posts_path = os.path.join(dirname, basename.replace("_response", "_posts").replace(".txt", ".json"))
            posts = load_posts(alt_posts_path)
        if not posts and dirname:
            alt_posts_path = os.path.join(dirname, "posts.json")
            posts = load_posts(alt_posts_path)
    if not posts:
        posts = MOCK_POSTS

    posts_by_id = {p.id: p for p in posts}

    if as_json:
        import json
        print(json.dumps([p.__dict__ for p in problems], indent=2))
    else:
        print_problems(problems, posts_by_id)


def cmd_run(
    query: str = "tracking subscriptions",
    posts_path: str = "posts.json",
    prompt_path: str = "prompt.txt",
    use_signals: bool = True,
    subreddit: str | None = None,
    as_json: bool = False,
) -> None:
    """
    Unified end-to-end command: fetch live Reddit data, persist the raw
    posts and the generated prompt locally (for full auditability), run
    the Gemini API analysis directly, and print the resulting report --
    all in a single step.

    Defaults to the high-intent Boolean signal search (use_signals=True)
    since that's the recommended search strategy.
    """
    import os

    from analyzer import analyze_posts_via_api_raw, build_full_prompt, parse_response
    from models import save_posts
    from reddit_client import search_reddit_for_problem_signals, search_reddit_posts

    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "Error: GEMINI_API_KEY is not set. Create a Gemini API key in Google AI Studio "
            "and set GEMINI_API_KEY before running this command."
        )
        return

    if use_signals:
        target = f"r/{subreddit}" if subreddit else "all Reddit"
        print(f"Searching for problem signals around: '{query}' ({target})...")
        posts = search_reddit_for_problem_signals(query, limit=50, subreddit=subreddit)
    else:
        target = f" in r/{subreddit}" if subreddit else ""
        print(f"Searching Reddit for query: '{query}'{target}...")
        posts = search_reddit_posts(query, subreddit=subreddit)

    if not posts:
        print(f"No posts found for '{query}'. Run aborted.")
        return

    save_posts(posts, posts_path)
    print(f"Saved {len(posts)} posts to '{posts_path}'.")

    prompt = build_full_prompt(posts)
    with open(prompt_path, "w") as f:
        f.write(prompt)
    print(f"Wrote prompt for {len(posts)} posts to '{prompt_path}' (for auditability).")

    # Also write timestamped copies to archives/ so this run's raw posts and
    # prompt survive future `run` calls, which otherwise overwrite
    # posts.json/prompt.txt in place every time.
    archive_posts_path, archive_prompt_path, archive_response_path = _archive_paths(query)
    save_posts(posts, archive_posts_path)
    with open(archive_prompt_path, "w") as f:
        f.write(prompt)

    print("Analyzing posts via the Gemini API...")
    posts_by_id = {p.id: p for p in posts}
    raw_text = analyze_posts_via_api_raw(posts)

    with open(archive_response_path, "w") as f:
        f.write(raw_text)
    print(f"Archived this run to '{archive_posts_path}', '{archive_prompt_path}', '{archive_response_path}'.")

    problems = parse_response(raw_text)

    if as_json:
        import json
        print(json.dumps([p.__dict__ for p in problems], indent=2))
    else:
        print_problems(problems, posts_by_id)


def print_usage() -> None:
    print(__doc__)


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]

    use_signals = "--signals" in args
    args = [a for a in args if a != "--signals"]

    subreddit = None
    for a in list(args):
        if a.startswith("--subreddit="):
            subreddit = a.split("=", 1)[1]
            args.remove(a)

    if not args:
        print_usage()
        return

    command = args[0]

    if command == "generate":
        query = "tracking subscriptions"
        output_path = "prompt.txt"
        if len(args) > 1:
            if args[1].endswith(".txt"):
                output_path = args[1]
            else:
                query = args[1]
                if len(args) > 2:
                    output_path = args[2]
        cmd_generate(
            query=query,
            output_path=output_path,
            use_signals=use_signals,
            subreddit=subreddit,
        )
    elif command == "parse":
        if len(args) < 2:
            print("Usage: python main.py parse <response_file>")
            sys.exit(1)
        cmd_parse(args[1], as_json=as_json)
    elif command in {"run", "run-api"}:
        query = args[1] if len(args) > 1 else "tracking subscriptions"
        cmd_run(
            query=query,
            use_signals=True,
            subreddit=subreddit,
            as_json=as_json,
        )
    else:
        print(f"Unknown command: {command}\n")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()