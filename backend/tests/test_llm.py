"""The chip model: prompt shape, answer parsing, and honest failure.

No network: `llm._post` is patched, or `requests.post` is patched to fail. The
point of these tests is that the call is never required — no key, a 500, a
timeout or JSON soup all return None, and the page keeps its static chips.
"""
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("GNANI_API_KEY", "test-key-not-used")

import llm  # noqa: E402


class AvailabilityTest(unittest.TestCase):
    def test_no_key_means_unavailable_and_no_call(self):
        with patch.dict(os.environ, {"LLM_API_KEY": ""}):
            self.assertFalse(llm.available())
            with patch.object(llm.requests, "post") as post:
                self.assertIsNone(llm.direct_reply("कल दस बजे आइए।", "hi-IN"))
            post.assert_not_called()

    def test_the_session_header_is_stable(self):
        self.assertTrue(llm.SESSION)
        self.assertEqual(llm.SESSION, llm.SESSION)


class PromptTest(unittest.TestCase):
    def _capture(self, content='["ठीक है।"]'):
        seen = {}

        def fake_post(messages, max_tokens=80):
            seen["messages"] = messages
            seen["max_tokens"] = max_tokens
            return content

        return seen, fake_post

    def test_the_caller_language_is_named_in_the_prompt(self):
        seen, fake = self._capture()
        with patch.object(llm, "_post", fake):
            self.assertEqual(llm.direct_reply("कल दस बजे आइए।", "hi-IN"),
                             "ठीक है।")
        system = seen["messages"][0]["content"]
        self.assertIn("Hindi", system)
        self.assertIn("Devanagari", system)
        self.assertIn("never invent", system.lower())

    def test_bengali_is_asked_for_in_bengali(self):
        seen, fake = self._capture('["হ্যাঁ।"]')
        with patch.object(llm, "_post", fake):
            self.assertEqual(llm.direct_reply("আপনি কেমন আছেন?", "bn-IN"),
                             "হ্যাঁ।")
        self.assertIn("Bengali", seen["messages"][0]["content"])

    def test_the_recent_lines_are_given_as_context(self):
        seen, fake = self._capture()
        with patch.object(llm, "_post", fake):
            llm.direct_reply("तीसरी बात", "hi-IN", ["पहली बात", "दूसरी बात"])
        user = seen["messages"][1]["content"]
        self.assertIn("पहली बात", user)
        self.assertIn("दूसरी बात", user)
        self.assertTrue(user.strip().endswith("last line: तीसरी बात"))

    def test_only_the_last_three_context_lines_are_sent(self):
        seen, fake = self._capture()
        with patch.object(llm, "_post", fake):
            llm.direct_reply("x", "hi-IN", ["a", "b", "c", "d", "e"])
        user = seen["messages"][1]["content"]
        self.assertNotIn("caller: a", user)
        self.assertIn("caller: e", user)


class ParseTest(unittest.TestCase):
    def _reply(self, content):
        with patch.object(llm, "_post", return_value=content):
            return llm.direct_reply("कल दस बजे आइए।", "hi-IN")

    def test_a_bare_json_array(self):
        self.assertEqual(self._reply('["ठीक है।"]'), "ठीक है।")

    def test_a_fenced_json_array(self):
        self.assertEqual(self._reply('```json\n["ठीक है।"]\n```'), "ठीक है।")

    def test_an_empty_array_is_no_answer(self):
        self.assertIsNone(self._reply("[]"))

    def test_a_non_string_item_is_skipped(self):
        self.assertEqual(self._reply('[42, "ठीक है।"]'), "ठीक है।")

    def test_json_soup_is_no_answer(self):
        self.assertIsNone(self._reply("I think the reply should be yes."))

    def test_an_object_is_not_an_array(self):
        self.assertIsNone(self._reply('{"reply": "ठीक है।"}'))

    def test_a_none_response_is_no_answer(self):
        self.assertIsNone(self._reply(None))


class SummaryTest(unittest.TestCase):
    """The card's model call: one JSON object, UI locale, no invented facts."""

    def _summary(self, content, lang="en"):
        with patch.object(llm, "_post", return_value=content) as post:
            value = llm.summary([
                {"who": "caller", "text": "नमस्ते, मैं डॉ. मेहरा की क्लिनिक से हूँ।"},
                {"who": "caller", "text": "कल दस बजे का समय खाली है।"},
                {"who": "me", "text": "हाँ, कल दस बजे आ जाऊँगी।"},
            ], lang)
        return value, post

    def test_a_json_object_is_parsed_and_capped(self):
        value, _ = self._summary(
            '{"who": "Dr. Mehra\'s clinic", "agreed": "tomorrow 10 a.m.", '
            '"next": "she will come at 10"}')
        self.assertEqual(value["who"], "Dr. Mehra's clinic")
        self.assertEqual(value["agreed"], "tomorrow 10 a.m.")
        self.assertEqual(value["next"], "she will come at 10")

    def test_the_ui_locale_is_named_in_the_prompt(self):
        _, post = self._summary('{"who":"x","agreed":"","next":""}', "hi")
        system = post.call_args[0][0][0]["content"]
        self.assertIn("Hindi", system)
        self.assertIn("never invent", system.lower())

    def test_a_transcript_of_only_one_side_still_summarises(self):
        with patch.object(llm, "_post",
                          return_value='{"who":"a","agreed":"b","next":""}'):
            value = llm.summary([{"who": "caller", "text": "hello"}])
        self.assertEqual(value, {"who": "a", "agreed": "b", "next": ""})

    def test_empty_strings_are_returned_not_dropped(self):
        value, _ = self._summary('{"who":"x","agreed":"","next":""}')
        self.assertEqual(value, {"who": "x", "agreed": "", "next": ""})

    def test_an_empty_transcript_makes_no_call(self):
        with patch.object(llm, "_post") as post:
            self.assertIsNone(llm.summary([]))
        post.assert_not_called()

    def test_an_object_in_fences_is_accepted(self):
        value, _ = self._summary(
            '```json\n{"who":"x","agreed":"y","next":"z"}\n```')
        self.assertEqual(value, {"who": "x", "agreed": "y", "next": "z"})

    def test_a_missing_field_is_no_answer(self):
        value, _ = self._summary('{"who":"x","agreed":"y"}')
        self.assertIsNone(value)

    def test_json_soup_is_no_answer(self):
        self.assertIsNone(self._summary("The call was about an appointment.")[0])


class TransportTest(unittest.TestCase):
    def test_a_500_is_no_answer(self):
        class Response:
            status_code = 500

            def json(self):
                raise AssertionError("must not parse a 500")

        with patch.object(llm.requests, "post", return_value=Response()):
            self.assertIsNone(llm._post([{"role": "user", "content": "x"}]))

    def test_a_network_error_is_no_answer(self):
        import requests as real_requests

        with patch.object(llm.requests, "post",
                          side_effect=real_requests.ConnectionError("down")):
            self.assertIsNone(llm._post([{"role": "user", "content": "x"}]))

    def test_the_request_carries_the_session_header_and_model(self):
        captured = {}

        class Response:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "[]"}}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, headers=headers, body=json,
                            timeout=timeout)
            return Response()

        with patch.dict(os.environ, {"LLM_API_KEY": "test-not-a-real-key"}), \
             patch.object(llm.requests, "post", fake_post):
            llm._post([{"role": "user", "content": "x"}])

        self.assertTrue(captured["url"].endswith("/chat/completions"))
        self.assertIn("opencode.ai/inference/go/openai/v1", captured["url"])
        self.assertEqual(captured["headers"]["x-opencode-session"], llm.SESSION)
        self.assertTrue(captured["headers"]["Authorization"].startswith("Bearer "))
        self.assertEqual(captured["body"]["model"], llm.MODEL)
        # The model is a reasoning one; thinking off is what keeps a chip to
        # ~2.5 s instead of 5-7 s (measured, LLM-NOTES.md).
        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})


if __name__ == "__main__":
    unittest.main()
