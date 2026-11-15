"""Reply chips: the model writes one answer, the table guarantees two options.

No network: this is the part that must hold even when the model is down, so it
is tested as data — every language's two safety options, the caller-language
lookup, and the three-chip cap the row on screen can show.
"""
import unittest

import chips


class FixedPhrasesTest(unittest.TestCase):
    def test_every_language_has_two_usable_options(self):
        for code, pair in chips.FIXED.items():
            self.assertEqual(len(pair), 2, code)
            for phrase in pair:
                self.assertTrue(phrase.strip(), code)
                self.assertLessEqual(len(phrase), chips.CHIP_MAX, code)

    def test_the_options_are_not_the_english_ones_in_another_script(self):
        for code, (repeat, slower) in chips.FIXED.items():
            if code == "en":
                continue
            self.assertNotEqual(repeat, chips.FIXED["en"][0], code)
            self.assertNotEqual(slower, chips.FIXED["en"][1], code)

    def test_the_language_is_read_from_a_region_tag(self):
        self.assertEqual(chips.fixed("hi-IN"), list(chips.FIXED["hi"]))
        self.assertEqual(chips.fixed("bn-IN"), list(chips.FIXED["bn"]))
        self.assertEqual(chips.fixed("ta-IN"), list(chips.FIXED["ta"]))
        self.assertEqual(chips.fixed("ml-IN"), list(chips.FIXED["ml"]))

    def test_a_bare_or_odd_code_still_lands(self):
        self.assertEqual(chips.fixed("hi"), list(chips.FIXED["hi"]))
        self.assertEqual(chips.fixed("BN-in"), list(chips.FIXED["bn"]))
        self.assertEqual(chips.fixed("mr_IN"), list(chips.FIXED["mr"]))

    def test_an_unknown_language_falls_back_to_english(self):
        for lang in ("xx-IN", "", None, "zz", "en-US", "ur-IN"):
            self.assertEqual(chips.fixed(lang), list(chips.FIXED["en"]), lang)


class ComposeTest(unittest.TestCase):
    def test_the_answer_comes_first_then_the_two_options(self):
        self.assertEqual(chips.for_transcript("hi-IN", "ठीक है, दस बजे।"), [
            "ठीक है, दस बजे।",
            "कृपया दोहराइए।",
            "थोड़ा धीरे बोलिए।",
        ])

    def test_no_answer_means_no_chips_so_the_page_keeps_its_static_ones(self):
        self.assertEqual(chips.for_transcript("hi-IN", None), [])
        self.assertEqual(chips.for_transcript("hi-IN", ""), [])
        self.assertEqual(chips.for_transcript("hi-IN", "   "), [])

    def test_an_answer_that_repeats_an_option_is_not_shown_twice(self):
        self.assertEqual(chips.for_transcript("hi-IN", "थोड़ा धीरे बोलिए।"), [
            "थोड़ा धीरे बोलिए।",
            "कृपया दोहराइए।",
        ])

    def test_a_long_answer_is_cut_to_one_line(self):
        answer = "यह एक बहुत लंबा जवाब है जो एक चिप में कभी नहीं आएगा " * 2
        out = chips.for_transcript("hi-IN", answer)
        self.assertEqual(len(out), 3)
        self.assertLessEqual(len(out[0]), chips.CHIP_MAX)
        self.assertTrue(out[0].endswith("…"))

    def test_whitespace_and_quotes_are_flattened(self):
        self.assertEqual(chips.one_line('  "ठीक   है।"  '), "ठीक है।")

    def test_at_most_three_chips(self):
        self.assertLessEqual(len(chips.for_transcript("bn-IN", "হ্যাঁ।")), 3)


if __name__ == "__main__":
    unittest.main()


class AcknowledgementTest(unittest.TestCase):
    """The word the caller hears while a reply is still being synthesised."""

    def test_every_shipped_language_has_a_short_acknowledgement(self):
        for code in chips.FIXED:
            phrase = chips.ack(code)
            self.assertTrue(phrase.strip(), code)
            self.assertLessEqual(len(phrase), 12, code)

    def test_an_unknown_language_gets_the_fallback_not_the_wrong_script(self):
        self.assertEqual(chips.ack("xx-YY"), chips.ACK[chips.FALLBACK])
        self.assertEqual(chips.ack(None), chips.ACK[chips.FALLBACK])

    def test_the_acknowledgement_is_one_line(self):
        for code in chips.FIXED:
            self.assertNotIn("\n", chips.ack(code), code)
