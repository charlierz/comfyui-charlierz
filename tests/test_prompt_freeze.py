from __future__ import annotations

import unittest

from nodes.PromptFreeze import PromptFreeze


class PromptFreezeNodeTests(unittest.TestCase):
    def test_outputs_live_text_and_updates_frozen_text_when_not_frozen(self):
        result = PromptFreeze().freeze("live", "old frozen", False)
        self.assertEqual(result["result"], ("live",))
        self.assertEqual(result["ui"], {"captured_text": ["live"]})

    def test_outputs_frozen_text_when_frozen(self):
        result = PromptFreeze().freeze("live", "frozen", True)
        self.assertEqual(result, ("frozen",))


if __name__ == "__main__":
    unittest.main()
