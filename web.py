"""Local browser UI for Problem Radar.

Run with ``python3 web.py`` and open http://127.0.0.1:8000.
The existing command-line workflow remains unchanged; this module is only an
HTTP adapter around the same Reddit search and Gemini analysis functions.
"""

from __future__ import annotations

import json
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

from analyzer import analyze_posts_via_api
from reddit_client import search_reddit_for_problem_signals


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
HISTORY_PATH = ROOT / "problem_radar_history.json"
HISTORY_LOCK = threading.Lock()


def _load_history() -> list[dict]:
    try:
        data = json.loads(HISTORY_PATH.read_text())
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(item: dict) -> None:
    with HISTORY_LOCK:
        history = _load_history()
        history = [existing for existing in history if existing.get("id") != item["id"]]
        history.insert(0, item)
        # Keep local history small; every entry includes its original evidence.
        HISTORY_PATH.write_text(json.dumps(history[:20], indent=2))


def _summary(item: dict) -> dict:
    return {
        "id": item["id"],
        "topic": item["topic"],
        "created_at": item["created_at"],
        "problem_count": len(item.get("problems", [])),
    }


def _clean_topic(value: object) -> str:
    topic = re.sub(r"\s+", " ", str(value or "")).strip()
    if not topic:
        raise ValueError("Enter a topic, problem, or keyword to start a radar.")
    if len(topic) > 160:
        raise ValueError("Keep the topic under 160 characters.")
    return topic


def run_radar(topic: str) -> dict:
    """Run the unchanged automated pipeline and serialize its genuine output."""
    posts = search_reddit_for_problem_signals(topic, limit=50)
    if not posts:
        raise RuntimeError(f'No relevant Reddit discussions were found for "{topic}". Try another lens.')

    problems = analyze_posts_via_api(posts)
    problems.sort(key=lambda problem: problem.opportunity_score, reverse=True)

    return {
        "id": uuid.uuid4().hex,
        "topic": topic,
        "created_at": datetime.now(UTC).isoformat(),
        "problems": [asdict(problem) for problem in problems[:5]],
        "posts": [asdict(post) for post in posts],
    }


class ProblemRadarHandler(SimpleHTTPRequestHandler):
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

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/history":
            return self._json(HTTPStatus.OK, [_summary(item) for item in _load_history()])
        if path.startswith("/api/history/"):
            entry_id = unquote(path.removeprefix("/api/history/"))
            item = next((entry for entry in _load_history() if entry.get("id") == entry_id), None)
            if item is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "That saved radar is no longer available."})
            return self._json(HTTPStatus.OK, item)
        return super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/search":
            return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            topic = _clean_topic(payload.get("topic"))
            result = run_radar(topic)
            _save_history(result)
            return self._json(HTTPStatus.OK, result)
        except (ValueError, RuntimeError) as error:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception:
            return self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Problem Radar could not complete this search. Check the server terminal for details."},
            )


class LocalServer(ThreadingHTTPServer):
    """Avoid a reverse-DNS lookup when binding a loopback-only development server."""

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_name, self.server_port = self.server_address


def main() -> None:
    server = LocalServer(("127.0.0.1", 8000), ProblemRadarHandler)
    print("Problem Radar is ready at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProblem Radar stopped.")


if __name__ == "__main__":
    main()
