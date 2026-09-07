import unittest
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import reddit_client as reddit


class RedditCooldownTests(unittest.TestCase):
    def error(self, **headers):
        message = Message()
        for name, value in headers.items():
            message[name.replace('_', '-')] = value
        return HTTPError('https://www.reddit.com/search.rss', 429, 'limited', message, None)

    def setUp(self):
        self.now = 1000.0
        self.patches = [
            patch.object(reddit, 'LAST_RSS_REQUEST_AT', 0.0),
            patch.object(reddit, 'RSS_COOLDOWN_UNTIL', 0.0),
            patch.object(reddit.time, 'monotonic', side_effect=lambda: self.now),
            patch.object(reddit.time, 'sleep', side_effect=self.sleep),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def sleep(self, seconds):
        self.now += seconds

    def response(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
        return response

    def test_headers_use_longer_estimate_and_round_up(self):
        self.assertEqual(reddit._retry_after_seconds(self.error(Retry_After='10', X_Ratelimit_Reset='58.2')), 59)
        for invalid in ('nan', 'inf', '-1', 'bad'):
            self.assertEqual(reddit._retry_after_seconds(self.error(Retry_After=invalid, X_Ratelimit_Reset='12')), 12)
        self.assertIsNone(reddit._retry_after_seconds(self.error()))

    def test_retry_waits_for_reset_and_reports_countdown(self):
        calls = []
        events = []
        def fetch(*args, **kwargs):
            calls.append(self.now)
            if len(calls) == 1:
                raise self.error(X_Ratelimit_Reset='58')
            return self.response()
        with patch.object(reddit.urllib.request, 'urlopen', side_effect=fetch):
            reddit._fetch_atom('https://www.reddit.com/search.rss', 'test', on_status=lambda stage, **details: events.append(details['message']))
        self.assertEqual(calls, [1000, 1060])
        self.assertTrue(any('59 seconds' in message for message in events))
        self.assertTrue(any('1 second…' in message for message in events))
        self.assertEqual(events[-1], 'Searching Reddit discussions…')

    def test_fallback_and_attempt_limit(self):
        with patch.object(reddit.urllib.request, 'urlopen', side_effect=self.error()) as fetch:
            with self.assertRaises(reddit.RedditRateLimitError) as raised:
                reddit._fetch_atom('https://www.reddit.com/search.rss', 'test')
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(self.now, 1130)
        self.assertEqual(raised.exception.retry_after_seconds, 65)

    def test_next_search_honors_cooldown_after_failure(self):
        with patch.object(reddit.urllib.request, 'urlopen', side_effect=self.error(X_Ratelimit_Reset='40')):
            with self.assertRaises(reddit.RedditRateLimitError):
                reddit._fetch_atom('https://www.reddit.com/search.rss', 'test', max_retries=1)
        calls = []
        def fetch(*args, **kwargs):
            calls.append(self.now)
            return self.response()
        with patch.object(reddit.urllib.request, 'urlopen', side_effect=fetch):
            reddit._fetch_atom('https://www.reddit.com/search.rss', 'test')
        self.assertEqual(calls, [1042])

    def test_long_cooldown_returns_without_early_request(self):
        with patch.object(reddit.urllib.request, 'urlopen', side_effect=self.error(X_Ratelimit_Reset='600')) as fetch:
            with self.assertRaises(reddit.RedditRateLimitError) as raised:
                reddit._fetch_atom('https://www.reddit.com/search.rss', 'test')
            self.assertEqual(raised.exception.retry_after_seconds, 602)
            with self.assertRaises(reddit.RedditRateLimitError):
                reddit._fetch_atom('https://www.reddit.com/search.rss', 'test')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.now, 1000)


if __name__ == '__main__':
    unittest.main()
