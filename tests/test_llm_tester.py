import threading
import unittest
from unittest.mock import Mock, patch

import requests

from llm_tester import extract_model_ids, fetch_model_ids, normalize_api_url, test_model_api, validate_config


class ConfigurationTests(unittest.TestCase):
    def test_urls_keep_paths_and_add_v1_once(self):
        self.assertEqual(normalize_api_url("https://api.example/v1/", "models"), "https://api.example/v1/models")
        self.assertEqual(normalize_api_url("https://api.example/proxy", "responses"), "https://api.example/proxy/v1/responses")

    def test_config_discards_legacy_model_ids(self):
        result = validate_config([{
            "name": "Example", "base_url": "https://api.example/v1", "api_key": "secret",
            "models": ["legacy-model"],
        }])
        self.assertEqual(set(result[0]), {"name", "base_url", "api_key"})

    def test_config_rejects_invalid_entries(self):
        with self.assertRaisesRegex(ValueError, "第 1 项"):
            validate_config([{"name": "Example", "base_url": "bad-url", "api_key": "secret"}])

    def test_model_ids_are_unique_and_sorted(self):
        models = extract_model_ids({"data": [{"id": "z"}, {"id": "A"}, {"id": "z"}, {"name": "ignored"}]})
        self.assertEqual(models, ["A", "z"])


class GeminiModelTests(unittest.TestCase):
    def setUp(self):
        self.interface = {"base_url": "https://api.example/proxy/v1beta", "api_key": "secret"}

    def test_urls_preserve_versions_proxy_paths_and_queries(self):
        for path, expected in (
            ("", "/v1beta"), ("/proxy", "/proxy/v1beta"),
            ("/v1beta/", "/v1beta"), ("/v1", "/v1"),
            ("/proxy/v1alpha/", "/proxy/v1alpha"),
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    normalize_api_url(f"https://api.example{path}?route=test#ignored", "models", "Gemini"),
                    f"https://api.example{expected}/models?route=test",
                )

    def test_model_names_are_normalized_filtered_and_deduplicated(self):
        models = extract_model_ids({"models": [
            {"name": "models/gemini-z", "supportedGenerationMethods": ["generateContent", "countTokens"]},
            {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/empty", "supportedGenerationMethods": []},
            {"name": "models/gemini-a"},
            {"name": "gemini-a"}, {"name": "models/"}, {"id": "ignored"}, None,
        ]}, "Gemini")
        self.assertEqual(models, ["gemini-a", "gemini-z"])

    def test_invalid_model_list_is_reported(self):
        for payload in (None, [], {"data": []}, {"models": {}}):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "models"):
                    extract_model_ids(payload, "Gemini")

    @patch("llm_tester.requests.get")
    def test_fetches_all_pages_with_api_key_header(self, get):
        get.side_effect = [
            Mock(json=Mock(return_value={"models": [{"name": "models/gemini-z"}], "nextPageToken": "page-2"})),
            Mock(json=Mock(return_value={"models": [{"name": "models/gemini-a"}, {"name": "models/gemini-z"}]})),
        ]
        self.assertEqual(fetch_model_ids(self.interface, "Gemini", timeout=7), ["gemini-a", "gemini-z"])
        self.assertEqual(get.call_count, 2)
        first, second = get.call_args_list
        self.assertEqual(first.args[0], "https://api.example/proxy/v1beta/models")
        self.assertEqual(first.kwargs["headers"]["x-goog-api-key"], "secret")
        self.assertNotIn("Authorization", first.kwargs["headers"])
        self.assertEqual(first.kwargs["timeout"], 7)
        self.assertEqual(first.kwargs["params"], {})
        self.assertEqual(second.kwargs["params"], {"pageToken": "page-2"})

    @patch("llm_tester.requests.get")
    def test_repeated_page_token_is_reported(self, get):
        get.return_value = Mock(json=Mock(return_value={"models": [], "nextPageToken": "same"}))
        with self.assertRaisesRegex(ValueError, "nextPageToken"):
            fetch_model_ids(self.interface, "Gemini")
        self.assertEqual(get.call_count, 2)

    @patch("llm_tester.requests.get")
    def test_fetch_stops_between_pages(self, get):
        stop_event = threading.Event()

        def response(*args, **kwargs):
            stop_event.set()
            return Mock(json=Mock(return_value={"models": [], "nextPageToken": "page-2"}))

        get.side_effect = response
        self.assertEqual(fetch_model_ids(self.interface, "Gemini", stop_event=stop_event), [])
        get.assert_called_once()

    @patch("llm_tester.requests.get")
    def test_fetch_propagates_http_errors(self, get):
        get.return_value.raise_for_status.side_effect = requests.HTTPError("HTTP 403")
        with self.assertRaises(requests.HTTPError):
            fetch_model_ids(self.interface, "Gemini")

    @patch("llm_tester.requests.get")
    def test_openai_fetch_remains_compatible(self, get):
        get.return_value = Mock(json=Mock(return_value={"data": [{"id": "model-x"}]}))
        interface = {"base_url": "https://api.example/v1", "api_key": "secret"}
        self.assertEqual(fetch_model_ids(interface, "Responses"), ["model-x"])
        self.assertEqual(get.call_args.args[0], "https://api.example/v1/models")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer secret")


class RequestModeTests(unittest.TestCase):
    @patch("llm_tester.requests.post")
    def test_responses_request_format(self, post):
        response = Mock(ok=True)
        post.return_value = response
        result = test_model_api({"base_url": "https://api.example/v1", "api_key": "secret"}, "model-x", "Responses", 5)
        self.assertEqual(result[0], "✅ 可用")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.example/v1/responses")
        self.assertEqual(kwargs["json"], {"model": "model-x", "input": "hi", "max_output_tokens": 5})

    @patch("llm_tester.requests.post")
    def test_chat_completions_request_format(self, post):
        post.return_value = Mock(ok=True)
        test_model_api({"base_url": "https://api.example", "api_key": "secret"}, "model-x", "Chat Completions", 5)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.example/v1/chat/completions")
        self.assertEqual(kwargs["json"]["messages"], [{"role": "user", "content": "hi"}])

    @patch("llm_tester.requests.post")
    def test_gemini_request_format(self, post):
        post.return_value = Mock(ok=True)
        for model in ("gemini-test", "models/gemini-test"):
            with self.subTest(model=model):
                result = test_model_api(
                    {"base_url": "https://api.example/proxy/v1beta", "api_key": "secret"},
                    model, "Gemini", 7,
                )
                self.assertEqual(result[0], "✅ 可用")
                args, kwargs = post.call_args
                self.assertEqual(args[0], "https://api.example/proxy/v1beta/models/gemini-test:generateContent")
                self.assertEqual(kwargs["json"], {
                    "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                    "generationConfig": {"maxOutputTokens": 5},
                })
                self.assertEqual(kwargs["headers"]["x-goog-api-key"], "secret")
                self.assertNotIn("Authorization", kwargs["headers"])
                self.assertEqual(kwargs["timeout"], 7)

    @patch("llm_tester.requests.post")
    def test_gemini_http_failure(self, post):
        post.return_value = Mock(ok=False, status_code=403, text="permission denied")
        result = test_model_api({"base_url": "https://api.example", "api_key": "secret"}, "gemini-test", "Gemini", 5)
        self.assertEqual(result[0], "❌ 失败")
        self.assertEqual(result[2], "HTTP 403: permission denied")
        self.assertEqual(result[3], "fail")

    @patch("llm_tester.requests.post")
    def test_gemini_timeout_and_connection_error(self, post):
        for error, status in (
            (requests.Timeout("timed out"), "❌ 超时"),
            (requests.ConnectionError("connection failed"), "❌ 错误"),
        ):
            with self.subTest(error=error):
                post.side_effect = error
                result = test_model_api({"base_url": "https://api.example", "api_key": "secret"}, "gemini-test", "Gemini", 5)
                self.assertEqual(result[0], status)
                self.assertEqual(result[3], "fail")

    @patch("llm_tester.requests.post")
    def test_invalid_url_returns_error_without_network_request(self, post):
        result = test_model_api({"base_url": "bad-url", "api_key": "secret"}, "gemini-test", "Gemini", 5)
        self.assertEqual(result[0], "❌ 错误")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
