"""Local browser UI for Problem Radar.

Run with ``python3 web.py`` and open http://127.0.0.1:8000.
The existing command-line workflow remains unchanged; this module is only an
HTTP adapter around the same Reddit search and Gemini analysis functions.
"""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from analyzer import analyze_posts_via_api, expand_topic_keywords_via_api
from reddit_client import search_reddit_for_problem_signals, search_reddit_posts


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
HISTORY_PATH = ROOT / "problem_radar_history.json"
SAVED_IDEAS_PATH = ROOT / "problem_radar_saved_ideas.json"
MAX_REQUEST_BODY_BYTES = 1_000_000
HISTORY_LOCK = threading.Lock()
SAVED_IDEAS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


class SearchInProgressError(RuntimeError):
    """Raised when a browser user tries to overlap anonymous RSS searches."""


def _load_history() -> list[dict]:
    try:
        data = json.loads(HISTORY_PATH.read_text())
        _restrict_local_file(HISTORY_PATH)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(item: dict) -> None:
    with HISTORY_LOCK:
        history = _load_history()
        history = [existing for existing in history if existing.get("id") != item["id"]]
        history.insert(0, item)
        # Keep local history small; every entry includes its original evidence.
        _write_local_json(HISTORY_PATH, history[:20])


def _delete_history(entry_id: str) -> bool:
    """Remove one locally saved radar and report whether it existed."""
    with HISTORY_LOCK:
        history = _load_history()
        updated = [item for item in history if item.get("id") != entry_id]
        if len(updated) == len(history):
            return False
        _write_local_json(HISTORY_PATH, updated)
        return True


def _load_saved_ideas() -> list[dict]:
    try:
        data = json.loads(SAVED_IDEAS_PATH.read_text())
        _restrict_local_file(SAVED_IDEAS_PATH)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _idea_key(topic: str, problem: dict) -> str:
    title = re.sub(r"\s+", " ", str(problem.get("title", "")).strip()).casefold()
    return f"{topic.casefold()}::{title}"


def _save_idea(item: dict) -> tuple[dict, bool]:
    """Store one full opportunity snapshot locally, without duplicating it."""
    with SAVED_IDEAS_LOCK:
        ideas = _load_saved_ideas()
        existing = next((idea for idea in ideas if idea.get("key") == item["key"]), None)
        if existing:
            return existing, False
        ideas.insert(0, item)
        _write_local_json(SAVED_IDEAS_PATH, ideas[:50])
        return item, True


def _delete_saved_idea(idea_id: str) -> bool:
    with SAVED_IDEAS_LOCK:
        ideas = _load_saved_ideas()
        updated = [idea for idea in ideas if idea.get("id") != idea_id]
        if len(updated) == len(ideas):
            return False
        _write_local_json(SAVED_IDEAS_PATH, updated)
        return True


def _restrict_local_file(path: Path) -> None:
    """Keep locally stored search content readable only by this user when possible."""
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write_local_json(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _restrict_local_file(path)


def _saved_idea_summary(item: dict) -> dict:
    problem = item.get("problem", {})
    return {
        "id": item.get("id"),
        "key": item.get("key"),
        "topic": item.get("topic", ""),
        "title": problem.get("title", "Untitled opportunity"),
        "description": problem.get("description", ""),
        "opportunity_score": problem.get("opportunity_score", 0),
        "saved_at": item.get("saved_at"),
    }


def _clean_saved_idea(payload: dict) -> dict:
    topic = _clean_topic(payload.get("topic"))
    problem = payload.get("problem")
    if not isinstance(problem, dict):
        raise ValueError("Choose an opportunity to save.")
    title = re.sub(r"\s+", " ", str(problem.get("title", "")).strip())
    if not title or len(title) > 300:
        raise ValueError("That opportunity cannot be saved.")
    posts = payload.get("posts", [])
    if not isinstance(posts, list):
        posts = []
    signals = payload.get("signals", [])
    if not isinstance(signals, list):
        signals = []
    return {
        "id": uuid.uuid4().hex,
        "key": _idea_key(topic, problem),
        "topic": topic,
        "signal_mode": str(payload.get("signal_mode", "basic")),
        "signals": [str(signal) for signal in signals[:3]],
        "saved_at": datetime.now(UTC).isoformat(),
        "problem": problem,
        "posts": posts,
    }


def _summary(item: dict) -> dict:
    return {
        "id": item["id"],
        "topic": item["topic"],
        "created_at": item["created_at"],
        "problem_count": len(item.get("problems", [])),
        "signal_mode": item.get("signal_mode", "basic"),
        "signals": item.get("signals", []),
    }


def _clean_topic(value: object) -> str:
    topic = re.sub(r"\s+", " ", str(value or "")).strip()
    if not topic:
        raise ValueError("Enter a topic, problem, or keyword to start a radar.")
    if len(topic) > 160:
        raise ValueError("Keep the topic under 160 characters.")
    return topic


def _clean_search_options(payload: dict) -> tuple[str, list[str]]:
    mode = str(payload.get("signal_mode", "basic")).lower()
    if mode not in {"basic", "custom", "smart"}:
        raise ValueError("Choose Basic, Custom, or Smart signals.")

    raw_signals = payload.get("custom_signals", [])
    if not isinstance(raw_signals, list):
        raise ValueError("Custom signals must be a list of up to three terms.")
    signals = []
    for raw_signal in raw_signals:
        signal = re.sub(r"\s+", " ", str(raw_signal or "")).strip()
        if signal and signal.casefold() not in {item.casefold() for item in signals}:
            signals.append(signal)
    if len(signals) > 3:
        raise ValueError("Use no more than three custom signals.")
    if any(len(signal) > 48 for signal in signals):
        raise ValueError("Keep each custom signal under 48 characters.")
    if mode == "custom" and not signals:
        raise ValueError("Add at least one focus term, or choose Basic search.")
    return mode, signals


def run_radar(topic: str, signal_mode: str = "basic", custom_signals: list[str] | None = None, on_status=None) -> dict:
    """Run the existing pipeline and report only milestones that actually occur."""
    def update(stage: str, **details) -> None:
        if on_status:
            on_status(stage, **details)

    custom_signals = custom_signals or []
    if signal_mode == "smart":
        update("signals", message="Choosing topic-specific search signals…", signal_mode=signal_mode)
        keywords = expand_topic_keywords_via_api(topic)[:3]
        keyword_source = "Gemini-generated signals" if os.environ.get("GEMINI_API_KEY") else "Built-in problem signals"
        update("searching", message="Searching discussions with Smart signals…", signal_mode=signal_mode, keywords=keywords, keyword_source=keyword_source)
        posts = search_reddit_for_problem_signals(topic, limit=50, keywords=keywords, allow_broad_fallback=False)
    elif signal_mode == "custom":
        keywords = custom_signals
        update("searching", message="Searching discussions with your focus terms…", signal_mode=signal_mode, keywords=keywords, keyword_source="Your focus terms")
        posts = search_reddit_for_problem_signals(topic, limit=50, keywords=keywords, allow_broad_fallback=False)
    else:
        keywords = []
        update("searching", message="Searching Reddit discussions about this topic…", signal_mode=signal_mode)
        posts = search_reddit_posts(topic, limit=50, delay_seconds=0.0)
    if not posts:
        raise RuntimeError(f'No relevant Reddit discussions were found for "{topic}". Try another lens.')

    update("analyzing", message="Analyzing recurring software opportunities…", signal_mode=signal_mode, keywords=keywords, post_count=len(posts))
    problems = analyze_posts_via_api(posts)
    problems.sort(key=lambda problem: problem.opportunity_score, reverse=True)
    update("ranking", message="Ranking software opportunities…", signal_mode=signal_mode, keywords=keywords, post_count=len(posts))

    return {
        "id": uuid.uuid4().hex,
        "topic": topic,
        "signal_mode": signal_mode,
        "signals": keywords,
        "created_at": datetime.now(UTC).isoformat(),
        "problems": [asdict(problem) for problem in problems[:5]],
        "posts": [asdict(post) for post in posts],
    }


def _set_job(job_id: str, **updates) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)


def _run_job(job_id: str, topic: str, signal_mode: str, custom_signals: list[str]) -> None:
    def progress(stage: str, **details) -> None:
        _set_job(job_id, status="running", stage=stage, **details)

    try:
        result = run_radar(topic, signal_mode=signal_mode, custom_signals=custom_signals, on_status=progress)
        _save_history(result)
        _set_job(job_id, status="complete", stage="complete", result=result)
    except (ValueError, RuntimeError) as error:
        _set_job(job_id, status="failed", stage="failed", error=str(error))
    except Exception:
        _set_job(job_id, status="failed", stage="failed", error="Problem Radar could not complete this search. Check the server terminal for details.")


def _start_job(topic: str, signal_mode: str, custom_signals: list[str]) -> dict:
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "topic": topic, "signal_mode": signal_mode, "keywords": custom_signals if signal_mode == "custom" else [], "status": "queued", "stage": "queued", "message": "Preparing your radar…"}
    with JOBS_LOCK:
        if any(existing["status"] in {"queued", "running"} for existing in JOBS.values()):
            raise SearchInProgressError("A radar is already running. Wait for it to finish before starting another search.")
        JOBS[job_id] = job
    threading.Thread(target=_run_job, args=(job_id, topic, signal_mode, custom_signals), daemon=True).start()
    return job


class ProblemRadarHandler(SimpleHTTPRequestHandler):
    server_version = "ProblemRadar"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:
        # Keep the local UI quiet; requests still surface as browser errors.
        return

    def _json(self, status: HTTPStatus, payload: dict | list) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "connect-src 'self'; "
            "img-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        super().end_headers()

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid request size.") from error
        if length < 0 or length > MAX_REQUEST_BODY_BYTES:
            raise ValueError("Request is too large.")
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("Request data must be an object.")
        return payload

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/history":
            return self._json(HTTPStatus.OK, [_summary(item) for item in _load_history()])
        if path == "/api/saved":
            return self._json(HTTPStatus.OK, [_saved_idea_summary(item) for item in _load_saved_ideas()])
        if path.startswith("/api/saved/"):
            idea_id = unquote(path.removeprefix("/api/saved/"))
            item = next((idea for idea in _load_saved_ideas() if idea.get("id") == idea_id), None)
            if item is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "That saved idea is no longer available."})
            return self._json(HTTPStatus.OK, item)
        if path.startswith("/api/history/"):
            entry_id = unquote(path.removeprefix("/api/history/"))
            item = next((entry for entry in _load_history() if entry.get("id") == entry_id), None)
            if item is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "That saved radar is no longer available."})
            return self._json(HTTPStatus.OK, item)
        if path.startswith("/api/jobs/"):
            job_id = unquote(path.removeprefix("/api/jobs/"))
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                payload = dict(job) if job else None
            if payload is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "That search job is no longer available."})
            return self._json(HTTPStatus.OK, payload)
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/search", "/api/saved"}:
            return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        try:
            payload = self._read_json_body()
            if path == "/api/saved":
                item, created = _save_idea(_clean_saved_idea(payload))
                return self._json(HTTPStatus.CREATED if created else HTTPStatus.OK, {"item": _saved_idea_summary(item), "created": created})
            topic = _clean_topic(payload.get("topic"))
            signal_mode, custom_signals = _clean_search_options(payload)
            job = _start_job(topic, signal_mode, custom_signals)
            return self._json(HTTPStatus.ACCEPTED, job)
        except SearchInProgressError as error:
            return self._json(HTTPStatus.CONFLICT, {"error": str(error)})
        except (ValueError, RuntimeError) as error:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception:
            return self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Problem Radar could not complete this search. Check the server terminal for details."},
            )

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/saved/"):
            idea_id = unquote(path.removeprefix("/api/saved/"))
            if not idea_id:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "Choose a saved idea to remove."})
            if not _delete_saved_idea(idea_id):
                return self._json(HTTPStatus.NOT_FOUND, {"error": "That saved idea is no longer available."})
            return self._json(HTTPStatus.OK, {"deleted": True})
        if not path.startswith("/api/history/"):
            return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        entry_id = unquote(path.removeprefix("/api/history/"))
        if not entry_id:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "Choose a saved radar to remove."})
        if not _delete_history(entry_id):
            return self._json(HTTPStatus.NOT_FOUND, {"error": "That saved radar is no longer available."})
        return self._json(HTTPStatus.OK, {"deleted": True})


class LocalServer(ThreadingHTTPServer):
    """Avoid a reverse-DNS lookup when binding a loopback-only development server."""

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name, self.server_port = self.server_address[:2]


def main() -> None:
    server = LocalServer(("127.0.0.1", 8000), ProblemRadarHandler)
    print("Problem Radar is ready at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProblem Radar stopped.")


if __name__ == "__main__":
    main()
