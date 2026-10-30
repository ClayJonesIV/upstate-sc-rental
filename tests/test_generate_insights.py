import importlib.util
import os
import sys
import types
from pathlib import Path
import unittest


class FakeMessages:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="offline response")])


class FakeAnthropicClient:
    def __init__(self, api_key):
        self.api_key = api_key
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

    def test_recognizes_retired_model_not_found_as_nonrecoverable(self):
        error = RuntimeError("not_found_error: model: retired-model")
        self.assertTrue(market_insights.is_nonrecoverable_model_error(error))
        self.assertFalse(market_insights.is_nonrecoverable_model_error(RuntimeError("temporary timeout")))


if __name__ == "__main__":
    unittest.main()
