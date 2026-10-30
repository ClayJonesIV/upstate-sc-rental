import importlib.util
import os
import sys
import types
from pathlib import Path
import unittest


class FakeMessages:
    def __init__(self):
        self.request = None
        self.count_requests = []

    def create(self, **kwargs):
        self.request = kwargs
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="offline response")])

    def count_tokens(self, **kwargs):
        self.count_requests.append(kwargs)
        return types.SimpleNamespace(input_tokens=123)


class FakeAnthropicClient:
    def __init__(self, api_key, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs
        self.messages = FakeMessages()


os.environ.setdefault("ANTHROPIC_API_KEY", "not-used-in-tests")
sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=FakeAnthropicClient)
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location("market_insights", SCRIPTS_DIR / "generate_insights.py")
market_insights = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(market_insights)


class InsightGeneratorTests(unittest.TestCase):
    def test_uses_approved_supported_model_with_existing_messages_arguments(self):
        response = market_insights.call_claude("offline prompt")
        request = market_insights.client.messages.request

        self.assertEqual(response, "offline response")
        self.assertEqual(market_insights.CLAUDE_MODEL, "claude-sonnet-5-5")
        self.assertEqual(request["model"], "claude-sonnet-5-5")
        self.assertEqual(request["max_tokens"], 2000)
        self.assertEqual(request["thinking"], {"type": "between_tools"})
        self.assertIn("system", request)
        self.assertEqual(request["messages"], [{"role": "user", "content": "offline prompt"}])

    def test_disables_sdk_retries_and_counts_the_same_request_shape(self):
        result = market_insights.preflight_input_token_budget([("regional", "offline prompt")])
        count_request = market_insights.client.messages.count_requests[-1]

        self.assertEqual(market_insights.client.kwargs["max_retries"], 0)
        self.assertEqual(result["input_tokens"], 123)
        self.assertEqual(result["planned_calls"], 1)
        self.assertEqual(count_request["model"], market_insights.CLAUDE_MODEL)
        self.assertEqual(count_request["thinking"], {"type": "between_tools"})
        self.assertEqual(count_request["messages"], [{"role": "user", "content": "offline prompt"}])

    def test_blocks_paid_analysis_when_the_exact_input_cap_is_exceeded(self):
        original_cap = market_insights.MAX_TOTAL_INPUT_TOKENS
        market_insights.MAX_TOTAL_INPUT_TOKENS = 122
        try:
            with self.assertRaisesRegex(ValueError, "exceeds cap"):
                market_insights.preflight_input_token_budget([("regional", "offline prompt")])
        finally:
            market_insights.MAX_TOTAL_INPUT_TOKENS = original_cap

    def test_recognizes_retired_model_not_found_as_nonrecoverable(self):
        error = RuntimeError("not_found_error: model: retired-model")
        self.assertTrue(market_insights.is_nonrecoverable_model_error(error))
        self.assertFalse(market_insights.is_nonrecoverable_model_error(RuntimeError("temporary timeout")))


if __name__ == "__main__":
    unittest.main()
