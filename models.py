"""
Core data models for Problem Radar.

Kept deliberately tiny and source-agnostic: today the `Post` objects come
from mock_data.py, but tomorrow they could come from the Reddit API, an
app-review scraper, or a forum crawler. Nothing downstream (analyzer.py)
needs to know the difference.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Post:
    """A single piece of discussion content (Reddit post, app review, forum thread, etc.)."""

    id: str                # short stable identifier, e.g. "p1"
    source: str             # e.g. "reddit", "app_store", "forum"
    title: str               # post title (empty string if the source has none, e.g. app reviews)
    body: str                # the actual text content
    subreddit: Optional[str] = None
    url: Optional[str] = None

    def as_prompt_text(self) -> str:
        """Render this post as compact text for inclusion in an LLM prompt."""
        header = f"[{self.id}] source={self.source}"
        if self.subreddit:
            header += f" subreddit={self.subreddit}"
        title_line = f"Title: {self.title}\n" if self.title else ""
        return f"{header}\n{title_line}Body: {self.body}"


@dataclass
class Problem:
    """A recurring problem identified across multiple posts."""

    title: str
    description: str
    post_count: int
    representative_post_ids: list[str] = field(default_factory=list)
    who_experiences: str = ""
    existing_workarounds: str = ""
    pain_level: int = 0            # 1-10
    opportunity_score: int = 0     # 1-100
    score_reasoning: str = ""


def save_posts(posts: list[Post], filepath: str = "posts.json") -> None:
    """Save a list of Post objects to a JSON file."""
    import json
    from dataclasses import asdict

    data = [asdict(p) for p in posts]
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_posts(filepath: str = "posts.json") -> list[Post]:
    """Load a list of Post objects from a JSON file, returning empty list if file doesn't exist."""
    import json

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
        fields = Post.__dataclass_fields__.keys()
        return [Post(**{k: v for k, v in item.items() if k in fields}) for item in data]
    except (FileNotFoundError, json.JSONDecodeError):
        return []

