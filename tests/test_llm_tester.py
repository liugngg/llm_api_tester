import unittest
from unittest.mock import Mock, patch

from llm_tester import extract_model_ids, normalize_api_url, test_model_api, validate_config


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


if __name__ == "__main__":
    unittest.main()
