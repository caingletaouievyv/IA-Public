# IA/backend/scripts/test/test_flashcard_provider.py
"""Unit tests for flashcard Groq provider calls and safe failure logging."""

import json
import logging
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import requests
from requests.exceptions import Timeout

from app.ai.client import AIProviderError, call_flashcard_batch


def _ok_response(content: str) -> MagicMock:
    response = MagicMock()
    response.ok = True
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    return response


class FlashcardProviderClientTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": '{"requested_card_count": 2}'},
        ]

    @patch("app.ai.client.requests.post")
    def test_successful_batch_returns_provider_content(self, post):
        post.return_value = _ok_response('{"cards": []}')
        result = call_flashcard_batch(self.messages, batch_size=2, batch_index=1, operation_id="op-1")
        self.assertEqual(result, '{"cards": []}')
        post.assert_called_once()
        _args, kwargs = post.call_args
        self.assertEqual(kwargs["timeout"], 60)
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})

    @patch("app.ai.client.requests.post")
    def test_http_503_raises_server_error_with_status(self, post):
        response = MagicMock()
        response.ok = False
        response.status_code = 503
        response.headers = {}
        response.json.return_value = {"error": {"message": "overloaded", "code": "server_error"}}
        response.text = json.dumps(response.json.return_value)
        post.return_value = response
        with self.assertRaises(AIProviderError) as ctx:
            call_flashcard_batch(self.messages, batch_size=2, batch_index=2, operation_id="op-503")
        self.assertEqual(ctx.exception.category, "server_error")
        self.assertEqual(ctx.exception.status_code, 503)

    @patch("app.ai.client.time.sleep")
    @patch("app.ai.client.requests.post")
    def test_http_429_retries_once_then_raises_rate_limit(self, post, sleep):
        rate_limited = MagicMock()
        rate_limited.ok = False
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1"}
        rate_limited.json.return_value = {"error": {"message": "rate limit exceeded"}}
        rate_limited.text = json.dumps(rate_limited.json.return_value)
        post.side_effect = [rate_limited, rate_limited]
        with self.assertRaises(AIProviderError) as ctx:
            call_flashcard_batch(self.messages, batch_size=2, batch_index=1, operation_id="op-429")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)
        self.assertEqual(ctx.exception.category, "rate_limit")
        self.assertEqual(ctx.exception.status_code, 429)

    @patch("app.ai.client.requests.post")
    def test_timeout_raises_timeout_category(self, post):
        post.side_effect = Timeout("timed out")
        with self.assertRaises(AIProviderError) as ctx:
            call_flashcard_batch(self.messages, batch_size=2, batch_index=1, operation_id="op-timeout")
        self.assertEqual(ctx.exception.category, "timeout")

    @patch("app.ai.client.requests.post")
    def test_invalid_json_body_raises_parse_error(self, post):
        response = MagicMock()
        response.ok = True
        response.status_code = 200
        response.headers = {}
        response.json.side_effect = json.JSONDecodeError("bad", "doc", 0)
        response.text = "not-json"
        post.return_value = response
        with self.assertRaises(AIProviderError) as ctx:
            call_flashcard_batch(self.messages, batch_size=2, batch_index=3, operation_id="op-parse")
        self.assertEqual(ctx.exception.category, "response_parse_error")

    @patch("app.ai.client.AI_KEY", "sk-test-secret-key-do-not-log")
    @patch("app.ai.client.requests.post")
    def test_failure_logs_do_not_include_secrets_or_prompts(self, post):
        response = MagicMock()
        response.ok = False
        response.status_code = 502
        response.headers = {}
        response.json.return_value = {"error": {"message": "bad gateway"}}
        response.text = json.dumps(response.json.return_value)
        post.return_value = response
        with self.assertLogs("app.ai.client", level=logging.WARNING) as logs:
            with self.assertRaises(AIProviderError):
                call_flashcard_batch(self.messages, batch_size=2, batch_index=1, operation_id="op-log")
        combined = "\n".join(logs.output)
        self.assertIn("flashcard_provider_failure", combined)
        self.assertIn("category=server_error", combined)
        self.assertIn("operation_id=op-log", combined)
        self.assertNotIn("sk-test-secret-key-do-not-log", combined)
        self.assertNotIn("Bearer", combined)
        self.assertNotIn("Return JSON only", combined)
        self.assertNotIn('{"requested_card_count"', combined)
        posted_headers = post.call_args.kwargs["headers"]
        self.assertIn("Authorization", posted_headers)
        self.assertNotIn("sk-test-secret-key-do-not-log", combined)


if __name__ == "__main__":
    unittest.main()
