import unittest
import os
from unittest.mock import patch

from models import Post, Problem
import reddit_client
from reddit_client import RedditRateLimitError
import analyzer
import web


class ModelSelectionTests(unittest.TestCase):
    def setUp(self):
        analyzer.GROQ_COOLDOWN_UNTIL.clear()

    def test_rejects_models_outside_the_curated_list(self):
        self.assertEqual(analyzer.DEFAULT_MODEL, "openai/gpt-oss-120b")
        self.assertEqual(web._clean_model(None), "openai/gpt-oss-120b")
        self.assertEqual(web._clean_model("openai/gpt-oss-120b"), "openai/gpt-oss-120b")
        self.assertEqual(web._clean_model("gemini-3.6-flash"), "gemini-3.6-flash")
        self.assertEqual(web._clean_model("gemini-3.1-flash-lite"), "gemini-3.1-flash-lite")
        with self.assertRaises(ValueError):
            web._clean_model("gemini-3.7-flash")
        with self.assertRaises(ValueError):
            web._clean_model("not-a-model")

    def test_smart_radar_uses_the_selected_model_for_both_ai_requests(self):
        post = Post(
            id="p1",
            source="reddit",
            title="I wish this was easier",
            body="A repeated problem",
            subreddit="testing",
            url="https://www.reddit.com/r/testing/comments/p1",
        )
        captured = {}

        def keywords(topic, model, on_fallback=None):
            captured["keyword_model"] = model
            return ["wish"]

        def analyze(posts, model, on_fallback=None):
            captured["analysis_model"] = model
            return analyzer.AnalysisResult(
                problems=[
                    Problem(
                        title=f"Problem {index}",
                        description="A concise problem.",
                        post_count=2,
                        opportunity_score=index,
                    )
                    for index in range(4)
                ],
                provider="groq",
                model=model,
            )

        with patch.object(web, "expand_topic_keywords_via_api", keywords), patch.object(
            web, "search_reddit_for_problem_signals", return_value=[post]
        ), patch.object(web, "analyze_posts_with_metadata", analyze):
            result = web.run_radar("test topic", signal_mode="smart", model="openai/gpt-oss-120b")

        self.assertEqual(result["model"], "openai/gpt-oss-120b")
        self.assertEqual(result["provider"], "groq")
        self.assertEqual(result["provider_model"], "openai/gpt-oss-120b")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(len(result["problems"]), 3)
        self.assertEqual(captured, {"keyword_model": "openai/gpt-oss-120b", "analysis_model": "openai/gpt-oss-120b"})

    def test_groq_is_primary_when_it_succeeds(self):
        expected = [Problem(title="Problem", description="Description", post_count=2)]
        with patch.object(analyzer, "_analyze_groq", return_value=expected) as groq, patch.object(
            analyzer, "_analyze_gemini"
        ) as gemini:
            result = analyzer.analyze_posts_with_metadata([], model=analyzer.GROQ_MODEL)

        self.assertEqual(result.problems, expected)
        self.assertEqual(result.provider, "groq")
        self.assertFalse(result.fallback_used)
        groq.assert_called_once()
        gemini.assert_not_called()

    def test_retryable_120b_failure_uses_20b_fallback(self):
        expected = [Problem(title="Fallback", description="Description", post_count=2)]
        fallbacks = []
        with patch.object(
            analyzer,
            "_analyze_groq",
            side_effect=[
                analyzer.GroqRequestError("120B rate limit", retryable=True),
                expected,
            ],
        ) as groq, patch.object(analyzer, "_analyze_gemini") as gemini:
            result = analyzer.analyze_posts_with_metadata(
                [],
                model=analyzer.GROQ_MODEL,
                on_fallback=lambda primary, fallback: fallbacks.append((primary, fallback)),
            )

        self.assertEqual(result.problems, expected)
        self.assertEqual(result.provider, "groq")
        self.assertEqual(result.model, analyzer.GROQ_FALLBACK_MODEL)
        self.assertTrue(result.fallback_used)
        self.assertEqual(
            fallbacks,
            [(analyzer.GROQ_MODEL, analyzer.GROQ_FALLBACK_MODEL)],
        )
        self.assertEqual(groq.call_count, 2)
        gemini.assert_not_called()

    def test_nonretryable_groq_failure_does_not_hide_configuration_error(self):
        with patch.object(
            analyzer,
            "_analyze_groq",
            side_effect=analyzer.GroqRequestError("Groq rejected the key", retryable=False),
        ) as groq, patch.object(analyzer, "_analyze_gemini") as gemini:
            with self.assertRaises(analyzer.GroqRequestError):
                analyzer.analyze_posts_with_metadata([], model=analyzer.GROQ_MODEL)

        groq.assert_called_once()
        gemini.assert_not_called()

    def test_groq_route_never_uses_automatic_gemini_fallback(self):
        retryable = analyzer.GroqRequestError("temporary Groq failure", retryable=True)
        with patch.object(analyzer, "_analyze_groq", side_effect=[retryable, retryable]), patch.object(
            analyzer, "_analyze_gemini"
        ) as gemini:
            with self.assertRaises(analyzer.ProviderUnavailableError):
                analyzer.analyze_posts_with_metadata([], model=analyzer.GROQ_MODEL)

        gemini.assert_not_called()

    def test_active_120b_cooldown_skips_directly_to_20b(self):
        expected = [Problem(title="Fallback", description="Description", post_count=2)]
        analyzer._start_groq_cooldown(analyzer.GROQ_MODEL, 60, now=100)
        fallbacks = []
        with patch.object(analyzer.time, "monotonic", return_value=110), patch.object(
            analyzer, "_analyze_groq", return_value=expected
        ) as groq:
            result = analyzer.analyze_posts_with_metadata(
                [],
                on_fallback=lambda primary, fallback: fallbacks.append((primary, fallback)),
            )

        self.assertEqual(result.model, analyzer.GROQ_FALLBACK_MODEL)
        self.assertTrue(result.fallback_used)
        groq.assert_called_once()
        self.assertEqual(groq.call_args.kwargs["model"], analyzer.GROQ_FALLBACK_MODEL)
        self.assertEqual(len(fallbacks), 1)

    def test_groq_retry_after_header_controls_the_cooldown(self):
        class Response:
            headers = {"retry-after": "2.2"}

        error = RuntimeError("rate limited")
        error.response = Response()

        self.assertEqual(analyzer._retry_after_seconds(error), 3)

    def test_smart_signals_use_20b_before_built_in_terms(self):
        fallbacks = []
        with patch.dict(os.environ, {"GROQ_API_KEY": "groq-test"}, clear=True), patch.object(
            analyzer,
            "_generate_groq_text",
            side_effect=[
                analyzer.GroqRequestError("120B busy", retryable=True),
                '["overwhelmed", "manual work", "frustrating"]',
            ],
        ):
            keywords = analyzer.expand_topic_keywords_via_api(
                "college students",
                on_fallback=lambda primary, fallback: fallbacks.append((primary, fallback)),
            )

        self.assertEqual(keywords, ["overwhelmed", "manual work", "frustrating"])
        self.assertEqual(len(fallbacks), 1)

    def test_web_reports_20b_fallback_while_analysis_continues(self):
        post = Post(id="p1", source="reddit", title="Problem", body="Repeated problem")
        statuses = []

        def analyze(posts, model, on_fallback=None):
            on_fallback(analyzer.GROQ_MODEL, analyzer.GROQ_FALLBACK_MODEL)
            return analyzer.AnalysisResult(
                problems=[],
                provider="groq",
                model=analyzer.GROQ_FALLBACK_MODEL,
                fallback_used=True,
            )

        with patch.object(web, "search_reddit_posts", return_value=[post]), patch.object(
            web, "analyze_posts_with_metadata", analyze
        ):
            result = web.run_radar(
                "test topic",
                on_status=lambda stage, **details: statuses.append((stage, details)),
            )

        self.assertEqual(result["provider_model"], analyzer.GROQ_FALLBACK_MODEL)
        self.assertTrue(result["fallback_used"])
        self.assertTrue(
            any(
                stage == "analyzing" and "using GPT-OSS 20B" in details.get("message", "")
                for stage, details in statuses
            )
        )

    def test_direct_gemini_selection_never_calls_groq(self):
        expected = [Problem(title="Gemini", description="Description", post_count=2)]
        with patch.object(analyzer, "_analyze_groq") as groq, patch.object(
            analyzer, "_analyze_gemini", return_value=expected
        ) as gemini:
            result = analyzer.analyze_posts_with_metadata([], model="gemini-3.6-flash")

        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.model, "gemini-3.6-flash")
        groq.assert_not_called()
        gemini.assert_called_once()

    def test_both_groq_models_unavailable_has_its_own_user_facing_failure(self):
        web.JOBS.clear()
        web.JOBS["test-job"] = {"status": "running"}
        with patch.object(
            web,
            "run_radar",
            side_effect=analyzer.ProviderUnavailableError("private provider details"),
        ):
            web._run_job("test-job", "test topic", "basic", [], analyzer.GROQ_MODEL)

        self.assertEqual(web.JOBS["test-job"]["error_type"], "provider_unavailable")
        self.assertNotIn("private", web.JOBS["test-job"]["error"])

    def test_recognizes_gemini_quota_errors(self):
        self.assertTrue(web._is_quota_error(RuntimeError("429 RESOURCE_EXHAUSTED: check quota")))
        self.assertFalse(web._is_quota_error(RedditRateLimitError()))
        self.assertFalse(web._is_quota_error(RuntimeError("Invalid API key")))

    def test_reddit_rate_limit_has_its_own_user_facing_failure(self):
        web.JOBS.clear()
        web.JOBS["test-job"] = {"status": "running"}
        with patch.object(web, "run_radar", side_effect=RedditRateLimitError(120)), patch.object(
            web.logger, "warning"
        ) as log_warning:
            web._run_job("test-job", "test topic", "basic", [], "gemini-3.6-flash")

        self.assertEqual(web.JOBS["test-job"]["error_type"], "reddit_rate_limit")
        self.assertEqual(web.JOBS["test-job"]["retry_after"], 120)
        self.assertIn("Reddit", web.JOBS["test-job"]["error"])
        log_warning.assert_called_once_with("Reddit rate-limited radar job (job_id=%s)", "test-job")

    def test_recognizes_temporary_gemini_high_demand_errors(self):
        self.assertTrue(web._is_model_busy_error(RuntimeError("503 UNAVAILABLE: model experiencing high demand")))
        self.assertFalse(web._is_model_busy_error(RuntimeError("429 RESOURCE_EXHAUSTED")))

    def test_uses_render_port_without_exposing_local_development(self):
        with patch.dict(os.environ, {"PORT": "10000"}, clear=False):
            self.assertEqual(web._server_address(), ("0.0.0.0", 10000))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(web._server_address(), ("127.0.0.1", 8000))

    def test_allows_three_successful_searches_per_fifteen_minutes(self):
        web.SEARCH_ATTEMPTS.clear()
        for _ in range(3):
            web._reserve_search_attempt("test-visitor", now=0)
        with self.assertRaises(web.SearchRateLimitError) as error:
            web._reserve_search_attempt("test-visitor", now=0)
        self.assertEqual(error.exception.retry_after_seconds, 900)
        web._reserve_search_attempt("test-visitor", now=901)

    def test_failed_search_refunds_its_reserved_attempt(self):
        web.JOBS.clear()
        web.SEARCH_ATTEMPTS.clear()
        attempt_at = web._reserve_search_attempt("test-visitor", now=10)
        web.JOBS["test-job"] = {"status": "running"}

        with patch.object(web, "run_radar", side_effect=RuntimeError("503 UNAVAILABLE: high demand")):
            web._run_job(
                "test-job",
                "test topic",
                "basic",
                [],
                "gemini-3.6-flash",
                "test-visitor",
                attempt_at,
            )

        self.assertNotIn("test-visitor", web.SEARCH_ATTEMPTS)
        self.assertEqual(web.JOBS["test-job"]["status"], "failed")

    def test_successful_search_keeps_its_reserved_attempt(self):
        web.JOBS.clear()
        web.SEARCH_ATTEMPTS.clear()
        attempt_at = web._reserve_search_attempt("test-visitor", now=10)
        web.JOBS["test-job"] = {"status": "running"}

        with patch.object(web, "run_radar", return_value={"id": "result"}):
            web._run_job(
                "test-job",
                "test topic",
                "basic",
                [],
                "gemini-3.6-flash",
                "test-visitor",
                attempt_at,
            )

        self.assertEqual(list(web.SEARCH_ATTEMPTS["test-visitor"]), [10])
        self.assertEqual(web.JOBS["test-job"]["status"], "complete")

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

    def test_malformed_model_response_is_not_exposed_to_the_browser(self):
        web.JOBS.clear()
        web.JOBS["test-job"] = {"status": "running"}
        private_detail = "Raw model response: private upstream content"
        with patch.object(web, "run_radar", side_effect=ValueError(private_detail)), patch.object(
            web.logger, "exception"
        ):
            web._run_job("test-job", "test topic", "basic", [], "gemini-3.1-flash-lite")

        self.assertNotIn(private_detail, web.JOBS["test-job"]["error"])
        self.assertEqual(
            web.JOBS["test-job"]["error"],
            "Problem Radar could not complete this search. Try again in a moment.",
        )

    def test_no_results_message_remains_user_facing(self):
        web.JOBS.clear()
        web.JOBS["test-job"] = {"status": "running"}
        safe_message = 'No relevant Reddit discussions were found for "test topic". Try another lens.'
        with patch.object(web, "run_radar", side_effect=web.NoRelevantDiscussionsError(safe_message)):
            web._run_job("test-job", "test topic", "basic", [], "gemini-3.1-flash-lite")

        self.assertEqual(web.JOBS["test-job"]["error"], safe_message)

    def test_reddit_fetch_rejects_non_reddit_addresses(self):
        with self.assertRaises(ValueError):
            reddit_client._fetch_atom("file:///etc/passwd", "test-agent", max_retries=1)

    def test_reddit_parser_rejects_oversized_or_declared_xml(self):
        oversized = b"x" * (reddit_client.MAX_RSS_RESPONSE_BYTES + 1)
        declared = b'<!DOCTYPE feed [<!ENTITY example "unsafe">]><feed>&example;</feed>'
        with self.assertRaises(RuntimeError):
            reddit_client._parse_atom_document(oversized)
        with self.assertRaises(RuntimeError):
            reddit_client._parse_atom_document(declared)

    def test_caps_each_post_and_the_full_ai_input(self):
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

    def test_groq_uses_a_smaller_free_tier_input_budget(self):
        posts = [
            Post(id=f"p{index}", source="reddit", title="Long post", body="x" * 2_000)
            for index in range(30)
        ]
        with patch.object(analyzer, "_generate_groq_text", return_value="[]") as generate:
            analyzer._analyze_groq(posts, api_key="test-key")

        prompt = generate.call_args.args[0]
        self.assertLess(len(prompt), len(analyzer._build_user_prompt(posts)))
        self.assertIn("[p24]", prompt)
        self.assertNotIn("[p25]", prompt)

    def test_gemini_uses_the_same_twenty_five_highest_ranked_posts(self):
        posts = [
            Post(id=f"p{index}", source="reddit", title="Post", body="Body")
            for index in range(30)
        ]
        with patch.object(analyzer, "analyze_posts_via_api_raw", return_value="[]") as analyze:
            analyzer._analyze_gemini(posts, api_key="test-key")

        analyzed_posts = analyze.call_args.args[0]
        self.assertEqual(len(analyzed_posts), 25)
        self.assertEqual(analyzed_posts[0].id, "p0")
        self.assertEqual(analyzed_posts[-1].id, "p24")


if __name__ == "__main__":
    unittest.main()
