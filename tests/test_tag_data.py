from __future__ import annotations

import unittest

from modules.tag_data import normalize_tag, strip_prompt_weight


class StripPromptWeightTests(unittest.TestCase):
    def test_strips_single_emphasis_parens(self):
        self.assertEqual(strip_prompt_weight("(blue hair)"), "blue hair")

    def test_strips_nested_emphasis_parens(self):
        self.assertEqual(strip_prompt_weight("((blue hair))"), "blue hair")
        self.assertEqual(strip_prompt_weight("(((blue hair)))"), "blue hair")

    def test_strips_explicit_weight(self):
        self.assertEqual(strip_prompt_weight("(blue hair:1.3)"), "blue hair")

    def test_strips_integer_weight(self):
        self.assertEqual(strip_prompt_weight("(blue hair:2)"), "blue hair")

    def test_strips_nested_weight(self):
        self.assertEqual(strip_prompt_weight("(((blue hair:1.2)))"), "blue hair")

    def test_preserves_name_parens(self):
        self.assertEqual(strip_prompt_weight("pearl (gemstone)"), "pearl (gemstone)")
        self.assertEqual(strip_prompt_weight("emilia (re:zero)"), "emilia (re:zero)")

    def test_preserves_name_parens_when_weighted(self):
        # User weighted a tag whose name itself contains parens.
        self.assertEqual(strip_prompt_weight("(pearl (gemstone))"), "pearl (gemstone)")
        self.assertEqual(
            strip_prompt_weight("(pearl (gemstone):1.3)"),
            "pearl (gemstone)",
        )

    def test_leaves_emoticon_colon_tags_untouched(self):
        self.assertEqual(strip_prompt_weight(":3"), ":3")
        self.assertEqual(strip_prompt_weight(":o"), ":o")

    def test_leaves_plain_tag_untouched(self):
        self.assertEqual(strip_prompt_weight("blue hair"), "blue hair")

    def test_trims_surrounding_whitespace(self):
        self.assertEqual(strip_prompt_weight("  (blue hair:1.3)  "), "blue hair")

    def test_unbalanced_parens_not_stripped(self):
        self.assertEqual(strip_prompt_weight("(blue hair"), "(blue hair")
        self.assertEqual(strip_prompt_weight("blue hair)"), "blue hair)")


class NormalizePromptTagTests(unittest.TestCase):
    def test_normalize_tag_replaces_spaces_with_underscores(self):
        self.assertEqual(normalize_tag("blue hair"), "blue_hair")

    def test_normalize_tag_keeps_weight_parens(self):
        # normalize_tag itself does not strip weight; callers wrap with
        # strip_prompt_weight when handling user input.
        self.assertEqual(normalize_tag("(blue hair:1.3)"), "(blue_hair:1.3)")

    def test_strip_then_normalize_matches_canonical_key(self):
        self.assertEqual(
            normalize_tag(strip_prompt_weight("(blue hair:1.3)")),
            "blue_hair",
        )
        self.assertEqual(
            normalize_tag(strip_prompt_weight("((blue hair))")),
            "blue_hair",
        )
        self.assertEqual(
            normalize_tag(strip_prompt_weight("(pearl (gemstone))")),
            "pearl_(gemstone)",
        )


if __name__ == "__main__":
    unittest.main()
