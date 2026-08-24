"""
Free Reddit search client — no API key, no OAuth, no billing.

Uses Reddit's public search.rss endpoint (https://www.reddit.com/search.rss),
which is unauthenticated, officially documented by Reddit
(https://www.reddit.com/wiki/rss), and was NOT affected by the 2023 API
pricing change or the 2026 shutdown of the unauthenticated .json endpoints —
those only affected the oauth.reddit.com JSON API, not the public RSS feeds.

Trade-offs vs. the paid/OAuth API (worth knowing):
  - Only title + a content snippet + permalink per post, no comments, no
    score/upvote data.
  - Max ~100 items per request, no deep pagination cursor.
  - Reddit rate-limits anonymous traffic per IP, so don't hammer it — this
    client sleeps briefly between requests and sends a descriptive
    User-Agent, both of which Reddit explicitly asks for.

This module's only public function, search_reddit_posts(), returns
list[Post] — the exact same type mock_data.MOCK_POSTS provides. Nothing in
analyzer.py needs to change to use this instead.
"""

import html
import re
import time
import urllib.error
import urllib.request
from urllib.parse import quote
from xml.etree import ElementTree

from models import Post

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# Reddit asks for a descriptive, non-generic User-Agent. Replace the contact
# info with your own if you're doing anything beyond quick local testing.
DEFAULT_USER_AGENT = "problem-radar-poc/0.1 (personal non-commercial project)"


def _strip_html(raw_html: str) -> str:
    """Turn the HTML snippet Reddit's RSS returns into plain text."""
    text = html.unescape(raw_html or "")
    text = re.sub(r"<[^>]+>", " ", text)          # drop tags
    text = re.sub(r"\s+", " ", text).strip()        # collapse whitespace
    return text


def _extract_subreddit(link: str) -> str:
    match = re.search(r"/r/([^/]+)/", link or "")
    return match.group(1) if match else "unknown"


def _extract_post_id(entry_id: str, link: str) -> str | None:
    # Reddit atom entry ids look like "t3_abc123"; keep just the short code.
    match = re.search(r"t3_([a-z0-9]+)", entry_id or "", re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: pull the id out of the permalink itself, e.g.
    # https://www.reddit.com/r/foo/comments/abc123/some_title/
    match = re.search(r"/comments/([a-z0-9]+)/", link or "", re.IGNORECASE)
    return match.group(1) if match else None


def _fetch_atom(
    url: str,
    user_agent: str,
    max_retries: int = 3,
    backoff_seconds: float = 8.0,
) -> ElementTree.Element:
    """
    Fetch and parse a Reddit atom feed, retrying with backoff if Reddit
    rate-limits us (HTTP 429). Anonymous RSS traffic gets rate-limited
    fairly aggressively, so a single 429 isn't necessarily a dead end —
    waiting a bit and retrying often succeeds.
    """
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})

    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read()
            return ElementTree.fromstring(data)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt < max_retries:
                    wait = backoff_seconds * attempt  # 8s, 16s, 24s...
                    print(f"    (rate-limited, waiting {wait:.0f}s before retry {attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Reddit rate-limited this request (HTTP 429) after "
                    f"{max_retries} attempts. Try again later, reduce how "
                    f"many queries you run per session, or increase delay_seconds."
                ) from e
            raise RuntimeError(f"Reddit returned HTTP {e.code} for {url}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach Reddit: {e.reason}") from e

    raise RuntimeError("Unexpected: retry loop exited without returning or raising")


EXCLUDED_NOISE_SUBREDDITS = {
    "bestofredditorupdates",
    "borupdates",
    "aitah",
    "relationship_advice",
    "movies",
    "natureismetal",
    "wisconsin",
    "unitedkingdom",
    "comics",
    "funny",
}


def _parse_entries(root: ElementTree.Element) -> list[Post]:
    posts = []
    for i, entry in enumerate(root.findall(f"{ATOM_NS}entry")):
        title_el = entry.find(f"{ATOM_NS}title")
        content_el = entry.find(f"{ATOM_NS}content")
        link_el = entry.find(f"{ATOM_NS}link")
        id_el = entry.find(f"{ATOM_NS}id")

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        body = _strip_html(content_el.text) if content_el is not None and content_el.text else ""
        link = link_el.get("href") if link_el is not None else ""
        entry_id = id_el.text if id_el is not None else ""

        # Reddit's search matches subreddits as well as posts. A real post
        # permalink always contains "/comments/"; a subreddit hit doesn't.
        # Skip anything that isn't an actual post — mixing subreddit blurbs
        # in with real posts would corrupt the problem analysis downstream.
        if "/comments/" not in link:
            continue

        post_id = _extract_post_id(entry_id, link)
        if post_id is None:
            continue

        sub = _extract_subreddit(link)
        if sub.lower() in EXCLUDED_NOISE_SUBREDDITS:
            continue

        posts.append(
            Post(
                id=post_id,
                source="reddit",
                subreddit=sub,
                title=title,
                body=body,
                url=link,
            )
        )
    return posts


def search_reddit_posts(
    query: str,
    limit: int = 50,
    sort: str = "relevance",
    subreddit: str | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    delay_seconds: float = 5.0,
) -> list[Post]:
    """
    Search Reddit for `query` and return up to `limit` posts as Post objects.

    Args:
        query: search text, e.g. "tracking subscriptions"
        limit: target number of posts (Reddit's RSS caps a single request at
            100; if you ask for more than 100 you'll still only get 100 —
            genuinely deep collection needs a different approach, see the
            module docstring)
        sort: "relevance", "new", "top", "comments", or "hot"
        subreddit: restrict the search to one subreddit, e.g. "personalfinance"
            (omit to search all of Reddit)
        user_agent: sent as the User-Agent header; Reddit asks for something
            descriptive rather than a generic default
        delay_seconds: pause after the request, being polite to Reddit's
            anonymous-traffic rate limit if you call this repeatedly in a
            loop. 5s is a safer default than 1s — anonymous RSS traffic gets
            rate-limited more aggressively than that in practice.

    Returns:
        list[Post], each with source="reddit". May return fewer than `limit`
        if Reddit simply doesn't have that many matching results.
    """
    request_limit = max(1, min(limit, 100))
    encoded_query = quote(query)

    if subreddit:
        url = (
            f"https://www.reddit.com/r/{subreddit}/search.rss"
            f"?q={encoded_query}&restrict_sr=1&sort={sort}&limit={request_limit}"
        )
    else:
        url = (
            f"https://www.reddit.com/search.rss"
            f"?q={encoded_query}&sort={sort}&limit={request_limit}"
        )

    root = _fetch_atom(url, user_agent)
    posts = _parse_entries(root)

    if delay_seconds:
        time.sleep(delay_seconds)

    return posts[:limit]


# Generic keywords people use when expressing a problem, unmet need, or bad workaround.
DEFAULT_PROBLEM_KEYWORDS = [
    "wish",
    "track",
    "annoying",
    "alternative",
    "recommend",
    "frustrating",
    "hate",
]


def build_problem_query(topic: str, keywords: list[str] | None = None) -> str:
    """Build a single high-intent Boolean query combining title matching with problem keywords."""
    kw_list = keywords or DEFAULT_PROBLEM_KEYWORDS
    or_clause = " OR ".join(f'"{kw}"' for kw in kw_list)
    return f'title:"{topic}" ({or_clause})'


def search_reddit_for_problem_signals(
    topic: str,
    limit: int = 50,
    keywords: list[str] | None = None,
    sort: str = "relevance",
    subreddit: str | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    delay_seconds: float = 0.0,
) -> list[Post]:
    """
    Higher-level search in ONE single HTTP request: combines topic with
    frustration/need keywords into a single Boolean OR query, avoiding
    multiple HTTP requests and eliminating rate limit (HTTP 429) risks.
    """
    query = build_problem_query(topic, keywords=keywords)
    posts = search_reddit_posts(
        query,
        limit=limit,
        sort=sort,
        subreddit=subreddit,
        user_agent=user_agent,
        delay_seconds=delay_seconds,
    )

    # Single-word topics combined with a strict title: match can be overly
    # narrow and starve the result set. If the signal query came back thin,
    # fall back to a broader plain-text search on the topic alone so callers
    # don't end up with an empty (or near-empty) dataset.
    if len(topic.split()) == 1 and len(posts) < 15:
        posts = search_reddit_posts(
            topic,
            limit=limit,
            sort=sort,
            subreddit=subreddit,
            user_agent=user_agent,
            delay_seconds=delay_seconds,
        )

    return posts


if __name__ == "__main__":
    # Quick manual smoke tests:
    #   python reddit_client.py "tracking subscriptions"
    #   python reddit_client.py "tracking subscriptions" --signals
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "tracking subscriptions"
    use_signals = "--signals" in sys.argv

    if use_signals:
        print(f"Searching for problem signals around: {query!r}\n")
        results = search_reddit_for_problem_signals(query, limit=50)
    else:
        results = search_reddit_posts(query, limit=10)

    print(f"Fetched {len(results)} posts for topic: {query!r}\n")
    for p in results:
        print(f"[{p.id}] r/{p.subreddit} — {p.title}")
        print(f"    {p.body[:120]}{'...' if len(p.body) > 120 else ''}")
        print(f"    {p.url}\n")