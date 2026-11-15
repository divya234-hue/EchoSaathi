"""Unit tests for the transcript guard: a guess is not a sentence."""
import os
import unittest

os.environ.setdefault("GNANI_API_KEY", "test-key-not-used")

from stt import looks_unusable  # noqa: E402


class LooksUnusableTest(unittest.TestCase):
    def test_empty_text_is_unusable(self):
        self.assertTrue(looks_unusable("", 800))

    def test_whitespace_only_is_unusable(self):
        self.assertTrue(looks_unusable("  \n\t ", 800))

    def test_punctuation_only_is_unusable(self):
        self.assertTrue(looks_unusable("...", 800))
        self.assertTrue(looks_unusable("?!", 800))
        self.assertTrue(looks_unusable("।।", 800))        # Devanagari danda

    def test_single_character_is_unusable(self):
        self.assertTrue(looks_unusable("a", 800))
        self.assertTrue(looks_unusable("क", 800))

    def test_normal_english_sentence_is_usable(self):
        self.assertFalse(looks_unusable("I need a doctor", 900))

    def test_normal_devanagari_sentence_is_usable(self):
        self.assertFalse(looks_unusable("मुझे डॉक्टर चाहिए", 900))

    def test_digits_are_usable(self):
        self.assertFalse(looks_unusable("1234", 900))

    def test_four_words_in_short_audio_is_unusable(self):
        # the real failure from the issue: noise answered with a sentence
        self.assertTrue(looks_unusable("Sir, क्या जमा करें?", 200))
        self.assertTrue(looks_unusable("one two three four", 399))

    def test_four_words_with_enough_audio_is_usable(self):
        self.assertFalse(looks_unusable("one two three four", 400))

    def test_three_words_in_short_audio_is_usable(self):
        self.assertFalse(looks_unusable("one two three", 200))

    def test_zero_audio_ms_does_not_crash(self):
        self.assertTrue(looks_unusable("one two three four", 0))


if __name__ == "__main__":
    unittest.main()
