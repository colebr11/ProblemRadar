"""Local browser UI for Problem Radar.

Run with ``python3 web.py`` and open http://127.0.0.1:8000.
The existing command-line workflow remains unchanged; this module is only an
HTTP adapter around the same Reddit search and Gemini analysis functions.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from analyzer import DEFAULT_MODEL, analyze_posts_via_api, expand_topic_keywords_via_api
from reddit_client import RedditRateLimitError, search_reddit_for_problem_signals, search_reddit_posts


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
MAX_REQUEST_BODY_BYTES = 1_000_000
SEARCH_LIMIT_COUNT = 3
SEARCH_LIMIT_WINDOW_SECONDS = 15 * 60
JOB_RETENTION_SECONDS = 15 * 60
ANALYSIS_MODELS = {
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
    "gemini-3.6-flash": "Gemini 3.6 Flash",
}
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
SEARCH_ATTEMPTS: dict[str, deque[float]] = {}
SEARCH_ATTEMPTS_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


class SearchInProgressError(RuntimeError):
    """Raised when a browser user tries to overlap anonymous RSS searches."""


class SearchRateLimitError(RuntimeError):
    """Raised when a visitor has used the public demo's recent search allowance."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("The public demo's current search allowance has been reached.")


class NoRelevantDiscussionsError(RuntimeError):
    """A safe, user-facing result when Reddit has no useful matches."""


def _reserve_search_attempt(client_id: str, now: float | None = None) -> float:
    """Reserve one recent-search slot until the radar succeeds or fails."""
    current_time = time.monotonic() if now is None else now
    with SEARCH_ATTEMPTS_LOCK:
        for identifier, attempts in list(SEARCH_ATTEMPTS.items()):
            while attempts and current_time - attempts[0] >= SEARCH_LIMIT_WINDOW_SECONDS:
                attempts.popleft()
            if not attempts:
                del SEARCH_ATTEMPTS[identifier]

        attempts = SEARCH_ATTEMPTS.setdefault(client_id, deque())
        if len(attempts) >= SEARCH_LIMIT_COUNT:
            retry_after = max(1, math.ceil(SEARCH_LIMIT_WINDOW_SECONDS - (current_time - attempts[0])))
            raise SearchRateLimitError(retry_after)
        attempts.append(current_time)
    return current_time


def _refund_search_attempt(client_id: str, attempt_at: float) -> None:
    """Return a reserved slot when a radar fails before producing results."""
    with SEARCH_ATTEMPTS_LOCK:
        attempts = SEARCH_ATTEMPTS.get(client_id)
        if not attempts:
            return
        try:
            attempts.remove(attempt_at)
        except ValueError:
            return
        if not attempts:
            del SEARCH_ATTEMPTS[client_id]


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


def _clean_model(value: object) -> str:
    model = str(value or DEFAULT_MODEL).strip()
    if model not in ANALYSIS_MODELS:
        raise ValueError("Choose one of the available Gemini analysis models.")
    return model


def _is_quota_error(error: Exception) -> bool:
    """Recognize Gemini's 429 RESOURCE_EXHAUSTED quota/rate-limit responses."""
    message = str(error).casefold()
    return (
        "resource_exhausted" in message
        or "quota exceeded" in message
        or "check quota" in message
        or ("gemini" in message and ("rate limit" in message or "429" in message))
    )


def _is_model_busy_error(error: Exception) -> bool:
    """Recognize Gemini's temporary 503 high-demand responses."""
    message = str(error).casefold()
    return "503" in message and ("unavailable" in message or "high demand" in message)


def run_radar(
    topic: str,
    signal_mode: str = "basic",
    custom_signals: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    on_status=None,
) -> dict:
    """Run the existing pipeline and report only milestones that actually occur."""
    def update(stage: str, **details) -> None:
        if on_status:
            on_status(stage, **details)

    custom_signals = custom_signals or []
    if signal_mode == "smart":
        update("signals", message="Choosing topic-specific search signals…", signal_mode=signal_mode)
        keywords = expand_topic_keywords_via_api(topic, model=model)[:3]
        keyword_source = "Gemini-generated signals" if os.environ.get("GEMINI_API_KEY") else "Built-in problem signals"
        update("searching", message="Searching discussions with Smart signals…", signal_mode=signal_mode, keywords=keywords, keyword_source=keyword_source)
        posts = search_reddit_for_problem_signals(topic, limit=75, keywords=keywords, allow_broad_fallback=False)
    elif signal_mode == "custom":
        keywords = custom_signals
        update("searching", message="Searching discussions with your focus terms…", signal_mode=signal_mode, keywords=keywords, keyword_source="Your focus terms")
        posts = search_reddit_for_problem_signals(topic, limit=75, keywords=keywords, allow_broad_fallback=False)
    else:
        keywords = []
        update("searching", message="Searching Reddit discussions about this topic…", signal_mode=signal_mode)
        posts = search_reddit_posts(topic, limit=75, delay_seconds=0.0)
    if not posts:
        raise NoRelevantDiscussionsError(
            f'No relevant Reddit discussions were found for "{topic}". Try another lens.'
        )

    update("analyzing", message="Analyzing recurring software opportunities…", signal_mode=signal_mode, keywords=keywords, post_count=len(posts))
    problems = analyze_posts_via_api(posts, model=model)
    problems.sort(key=lambda problem: problem.opportunity_score, reverse=True)
    update("ranking", message="Ranking software opportunities…", signal_mode=signal_mode, keywords=keywords, post_count=len(posts))

    return {
        "id": uuid.uuid4().hex,
        "topic": topic,
        "model": model,
        "signal_mode": signal_mode,
        "signals": keywords,
        "created_at": datetime.now(UTC).isoformat(),
        "problems": [asdict(problem) for problem in problems[:3]],
        "posts": [asdict(post) for post in posts],
    }


def _set_job(job_id: str, **updates) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            if updates.get("status") in {"complete", "failed"}:
                updates["finished_at"] = time.monotonic()
            JOBS[job_id].update(updates)


def _prune_finished_jobs_locked(now: float | None = None) -> None:
    """Discard completed in-memory jobs after the browser has had time to collect them."""
    current_time = time.monotonic() if now is None else now
    for job_id, job in list(JOBS.items()):
        finished_at = job.get("finished_at")
        if (
            job.get("status") in {"complete", "failed"}
            and isinstance(finished_at, (int, float))
            and current_time - finished_at >= JOB_RETENTION_SECONDS
        ):
            del JOBS[job_id]


def _run_job(
    job_id: str,
    topic: str,
    signal_mode: str,
    custom_signals: list[str],
    model: str,
    client_id: str | None = None,
    attempt_at: float | None = None,
) -> None:
    def progress(stage: str, **details) -> None:
        _set_job(job_id, status="running", stage=stage, **details)

    completed = False
    try:
        result = run_radar(topic, signal_mode=signal_mode, custom_signals=custom_signals, model=model, on_status=progress)
        _set_job(job_id, status="complete", stage="complete", result=result)
        completed = True
    except RedditRateLimitError as error:
        logger.warning("Reddit rate-limited radar job (job_id=%s)", job_id)
        _set_job(
            job_id,
            status="failed",
            stage="failed",
            error_type="reddit_rate_limit",
            error=str(error),
            retry_after=error.retry_after_seconds,
        )
    except NoRelevantDiscussionsError as error:
        logger.info("No relevant discussions for radar job (job_id=%s)", job_id)
        _set_job(job_id, status="failed", stage="failed", error=str(error))
    except (ValueError, RuntimeError) as error:
        if _is_quota_error(error):
            logger.warning("Gemini quota blocked radar job (job_id=%s, model=%s)", job_id, model)
            _set_job(
                job_id,
                status="failed",
                stage="failed",
                error_type="quota",
                error="Gemini has reached a limit for this model right now.",
            )
        elif _is_model_busy_error(error):
            logger.warning("Gemini was busy for radar job (job_id=%s, model=%s)", job_id, model)
            _set_job(
                job_id,
                status="failed",
                stage="failed",
                error_type="model_busy",
                error="Gemini is temporarily busy for this model.",
            )
        else:
            logger.exception("Radar job failed (job_id=%s, model=%s)", job_id, model)
            _set_job(
                job_id,
                status="failed",
                stage="failed",
                error="Problem Radar could not complete this search. Try again in a moment.",
            )
    except Exception:
        # Keep implementation details out of the public response while preserving
        # the traceback in local or Render logs for diagnosis.
        logger.exception("Radar job failed (job_id=%s, model=%s)", job_id, model)
        _set_job(job_id, status="failed", stage="failed", error="Problem Radar could not complete this search. Try again in a moment.")
    finally:
        if not completed and client_id is not None and attempt_at is not None:
            _refund_search_attempt(client_id, attempt_at)
            logger.info("Refunded failed radar attempt (job_id=%s)", job_id)


def _start_job(topic: str, signal_mode: str, custom_signals: list[str], model: str, client_id: str) -> dict:
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "topic": topic, "model": model, "signal_mode": signal_mode, "keywords": custom_signals if signal_mode == "custom" else [], "status": "queued", "stage": "queued", "message": "Preparing your search…"}
    with JOBS_LOCK:
        _prune_finished_jobs_locked()
        if any(existing["status"] in {"queued", "running"} for existing in JOBS.values()):
            raise SearchInProgressError("A radar is already running. Wait for it to finish before starting another search.")
        attempt_at = _reserve_search_attempt(client_id)
        JOBS[job_id] = job
    threading.Thread(
        target=_run_job,
        args=(job_id, topic, signal_mode, custom_signals, model, client_id, attempt_at),
        daemon=True,
    ).start()
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
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Request data must be valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request data must be an object.")
        return payload

    def _client_id(self) -> str:
        """Use the visitor address Render forwards; fall back to the direct client address locally."""
        forwarded_for = self.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        return self.client_address[0]

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/jobs/"):
            job_id = unquote(path.removeprefix("/api/jobs/"))
            with JOBS_LOCK:
                _prune_finished_jobs_locked()
                job = JOBS.get(job_id)
                payload = dict(job) if job else None
            if payload is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "That search job is no longer available."})
            return self._json(HTTPStatus.OK, payload)
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/search":
            return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        try:
            payload = self._read_json_body()
            topic = _clean_topic(payload.get("topic"))
            signal_mode, custom_signals = _clean_search_options(payload)
            model = _clean_model(payload.get("model"))
            job = _start_job(topic, signal_mode, custom_signals, model, self._client_id())
            return self._json(HTTPStatus.ACCEPTED, job)
        except SearchRateLimitError as error:
            return self._json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {
                    "error": str(error),
                    "error_type": "rate_limit",
                    "retry_after": error.retry_after_seconds,
                },
            )
        except SearchInProgressError as error:
            return self._json(HTTPStatus.CONFLICT, {"error": str(error)})
        except ValueError as error:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception:
            logger.exception("Could not start a radar job")
            return self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Problem Radar could not complete this search. Try again in a moment."},
            )

    def do_DELETE(self) -> None:
        return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})


class LocalServer(ThreadingHTTPServer):
    """Avoid a reverse-DNS lookup when binding the local or hosted server."""

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name, self.server_port = self.server_address[:2]


def _server_address() -> tuple[str, int]:
    """Use Render's public binding when it supplies a port; stay loopback-only locally."""
    render_port = os.environ.get("PORT")
    if render_port:
        # Render requires its assigned port to listen on every container interface.
        return "0.0.0.0", int(render_port)  # nosec B104
    return "127.0.0.1", 8000


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host, port = _server_address()
    server = LocalServer((host, port), ProblemRadarHandler)
    if host == "127.0.0.1":
        print("Problem Radar is ready at http://127.0.0.1:8000")
    else:
        print(f"Problem Radar is ready on port {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProblem Radar stopped.")


if __name__ == "__main__":
    main()
