"""Unit tests for harness.wer — pure functions, no network, no key."""
import unittest

from harness import wer


class NormalizeTest(unittest.TestCase):
    def test_strips_punctuation_and_danda(self):
        self.assertEqual(wer.normalize("मेरा नाम गौतम है।"), "मेरा नाम गौतम है")

    def test_folds_nukta(self):
        # ज़ and ज are the same sound; counting them apart measures the writer.
        self.assertEqual(wer.normalize("हज़ार"), wer.normalize("हजार"))

    def test_folds_candrabindu(self):
        self.assertEqual(wer.normalize("पाँच"), wer.normalize("पांच"))

    def test_maps_devanagari_digits(self):
        self.assertEqual(wer.normalize("२०० रुपये"), "200 रुपये")

    def test_collapses_whitespace(self):
        # nukta is folded too, so हजार is the expected form
        self.assertEqual(wer.normalize("  दो   हज़ार  "), "दो हजार")


class WerTest(unittest.TestCase):
    def test_identical_is_zero(self):
        self.assertEqual(wer.wer("मैं ठीक हूँ", "मैं ठीक हूँ"), 0.0)

    def test_one_substitution(self):
        self.assertAlmostEqual(wer.wer("मैं ठीक हूँ", "मैं अच्छा हूँ"), 1 / 3)

    def test_deletion(self):
        self.assertAlmostEqual(wer.wer("कल सुबह दस बजे", "कल दस बजे"), 1 / 4)

    def test_empty_hypothesis_is_all_wrong(self):
        self.assertEqual(wer.wer("कल दस बजे", ""), 1.0)

    def test_both_empty(self):
        self.assertEqual(wer.wer("", ""), 0.0)

    def test_punctuation_and_nukta_are_not_errors(self):
        self.assertEqual(wer.wer("मेरा नाम गौतम है।", "मेरा नाम गौतम है"), 0.0)
        self.assertEqual(wer.wer("दो हज़ार रुपये", "दो हजार रुपये"), 0.0)

    def test_digits_match_words_only_after_normalisation_is_skipped(self):
        # 2,500 vs "दो हज़ार पाँच सौ" really is a mismatch; the harness avoids it
        # by asking the API for format=verbatim. Document the behaviour here.
        self.assertEqual(wer.wer("दो हज़ार पाँच सौ", "2,500"), 1.0)


class CerTest(unittest.TestCase):
    def test_cer_ignores_spacing(self):
        self.assertEqual(wer.cer("मैं ठीक", "मैंठीक"), 0.0)

    def test_cer_is_finer_than_wer(self):
        ref, hyp = "मैं ठीक हूँ", "मैं ठीक हू"
        self.assertLess(wer.cer(ref, hyp), wer.wer(ref, hyp))


class BengaliMetricTest(unittest.TestCase):
    """D-015: Bengali is reported unfolded until a native speaker checks it.

    These tests pin a decision, not a bug. If Bengali folding is added, it is a
    language decision: change these tests and D-015 in the same PR, and re-run
    the sweep so the published number moves with the metric.
    """

    def test_bengali_nukta_is_not_folded(self):
        # ড় and ড are distinct letters in Bengali; D-007's nukta fold is
        # Devanagari-only until #12 is settled.
        self.assertNotEqual(wer.normalize("ড়"), wer.normalize("ড"))

    def test_bengali_chandrabindu_is_not_folded(self):
        self.assertNotEqual(wer.normalize("পাঁচ"), wer.normalize("পাঁচং"))

    def test_devanagari_fold_is_script_specific(self):
        # The fold still holds where it was decided...
        self.assertEqual(wer.normalize("ज़"), wer.normalize("ज"))
        self.assertEqual(wer.normalize("हँस"), wer.normalize("हंस"))

    def test_bengali_spelling_variant_scores_as_an_error(self):
        # The consequence, pinned: পাঁচশো / পাঁচশ costs word accuracy today.
        self.assertGreater(wer.wer("পাঁচশো টাকা", "পাঁচশ টাকা"), 0.0)


if __name__ == "__main__":
    unittest.main()
