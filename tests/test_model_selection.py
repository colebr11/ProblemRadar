import unittest
import os
from unittest.mock import patch

from models import Post, Problem
import analyzer
import web


class ModelSelectionTests(unittest.TestCase):
    def test_rejects_models_outside_the_curated_list(self):
        self.assertEqual(web._clean_model("gemini-3.7-flash"), "gemini-3.7-flash")
        self.assertEqual(web._clean_model("gemini-3.1-flash-lite"), "gemini-3.1-flash-lite")
        with self.assertRaises(ValueError):
            web._clean_model("not-a-model")

    def test_smart_radar_uses_the_selected_model_for_both_gemini_requests(self):
        post = Post(
            id="p1",
            source="reddit",
            title="I wish this was easier",
            body="A repeated problem",
            subreddit="testing",
            url="https://www.reddit.com/r/testing/comments/p1",
        )
        captured = {}

        def keywords(topic, model):
            captured["keyword_model"] = model
            return ["wish"]

        def analyze(posts, model):
            captured["analysis_model"] = model
            return [
                Problem(
                    title=f"Problem {index}",
                    description="A concise problem.",
                    post_count=2,
                    opportunity_score=index,
                )
                for index in range(4)
            ]

        with patch.object(web, "expand_topic_keywords_via_api", keywords), patch.object(
            web, "search_reddit_for_problem_signals", return_value=[post]
        ), patch.object(web, "analyze_posts_via_api", analyze):
            result = web.run_radar("test topic", signal_mode="smart", model="gemini-3.7-flash")

        self.assertEqual(result["model"], "gemini-3.7-flash")
        self.assertEqual(len(result["problems"]), 3)
        self.assertEqual(captured, {"keyword_model": "gemini-3.7-flash", "analysis_model": "gemini-3.7-flash"})

    def test_recognizes_gemini_quota_errors(self):
        self.assertTrue(web._is_quota_error(RuntimeError("429 RESOURCE_EXHAUSTED: check quota")))
        self.assertFalse(web._is_quota_error(RuntimeError("Invalid API key")))

    def test_recognizes_temporary_gemini_high_demand_errors(self):
        self.assertTrue(web._is_model_busy_error(RuntimeError("503 UNAVAILABLE: model experiencing high demand")))
        self.assertFalse(web._is_model_busy_error(RuntimeError("429 RESOURCE_EXHAUSTED")))

    def test_uses_render_port_without_exposing_local_development(self):
        with patch.dict(os.environ, {"PORT": "10000"}, clear=False):
            self.assertEqual(web._server_address(), ("0.0.0.0", 10000))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(web._server_address(), ("127.0.0.1", 8000))

    def test_allows_three_searches_per_fifteen_minutes(self):
        web.SEARCH_ATTEMPTS.clear()
        for _ in range(3):
            web._record_search_attempt("test-visitor", now=0)
        with self.assertRaises(web.SearchRateLimitError) as error:
            web._record_search_attempt("test-visitor", now=0)
        self.assertEqual(error.exception.retry_after_seconds, 900)
        web._record_search_attempt("test-visitor", now=901)

    def test_discards_finished_jobs_after_fifteen_minutes(self):
        web.JOBS.clear()
        web.JOBS.update(
            {
                "complete": {"status": "complete", "finished_at": 0},
                "failed": {"status": "failed", "finished_at": 0},
                "recent": {"status": "complete", "finished_at": 1},
                "running": {"status": "running"},
            }
        )

        web._prune_finished_jobs_locked(now=web.JOB_RETENTION_SECONDS)

        self.assertNotIn("complete", web.JOBS)
        self.assertNotIn("failed", web.JOBS)
        self.assertIn("recent", web.JOBS)
        self.assertIn("running", web.JOBS)

    def test_unexpected_job_failure_is_logged_without_exposing_details(self):
        web.JOBS.clear()
        web.JOBS["test-job"] = {"status": "running"}
        with patch.object(web, "run_radar", side_effect=OSError("private implementation detail")), patch.object(
            web.logger, "exception"
        ) as log_exception:
            web._run_job("test-job", "private topic", "basic", [], "gemini-3.6-flash")

        self.assertEqual(web.JOBS["test-job"]["status"], "failed")
        self.assertEqual(
            web.JOBS["test-job"]["error"],
            "Problem Radar could not complete this search. Try again in a moment.",
        )
        log_exception.assert_called_once_with(
            "Radar job failed (job_id=%s, model=%s)", "test-job", "gemini-3.6-flash"
        )

    def test_caps_each_post_and_the_full_gemini_input(self):
        posts = [
            Post(id=f"p{index}", source="reddit", title="Long post", body="x" * 20)
            for index in range(2)
        ]
        with patch.object(analyzer, "MAX_POST_BODY_CHARS", 10), patch.object(
            analyzer, "MAX_TOTAL_POST_BODY_CHARS", 12
        ):
            prompt = analyzer._build_user_prompt(posts)

        self.assertEqual(prompt.count("xxxxxx [truncated]"), 2)
        self.assertNotIn("xxxxxxx", prompt)


if __name__ == "__main__":
    unittest.main()
