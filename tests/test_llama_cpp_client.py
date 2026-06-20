from __future__ import annotations

import unittest
from unittest.mock import patch


class LlamaCppClientUnloadTests(unittest.TestCase):
    def test_unload_model_swallows_errors(self):
        from modules.llama_cpp_client import unload_model

        with patch("modules.llama_cpp_client.post_json", side_effect=RuntimeError("server down")):
            result = unload_model("http://localhost:8080", "test-model")

        self.assertIsNone(result)

    def test_unload_model_returns_response_on_success(self):
        from modules.llama_cpp_client import unload_model

        with patch("modules.llama_cpp_client.post_json", return_value={"status": "ok"}):
            result = unload_model("http://localhost:8080", "test-model")

        self.assertEqual(result, {"status": "ok"})


class LlamaCppInputTypesTests(unittest.TestCase):
    def test_model_inputs_remain_dropdowns_with_custom_validation(self):
        from nodes.LlamaCpp import LlamaCppChat, LlamaCppVisionChat

        self.assertEqual(LlamaCppChat.INPUT_TYPES()["required"]["model"], ([""],))
        self.assertEqual(LlamaCppVisionChat.INPUT_TYPES()["required"]["model"], ([""],))
        self.assertTrue(LlamaCppChat.VALIDATE_INPUTS(model="dynamic-model"))
        self.assertTrue(LlamaCppVisionChat.VALIDATE_INPUTS(model="dynamic-model"))
        self.assertEqual(LlamaCppChat.VALIDATE_INPUTS(model=""), "model is required")


class LlamaCppChatErrorHandlingTests(unittest.TestCase):
    def test_chat_error_is_not_masked_by_unload_failure(self):
        from nodes.LlamaCpp import LlamaCppChat

        with (
            patch("nodes.LlamaCpp.post_json", side_effect=RuntimeError("chat failed")),
            patch("nodes.LlamaCpp.unload_model") as mock_unload,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                LlamaCppChat().chat(
                    server_url="http://localhost:8080",
                    model="test-model",
                    system_prompt="",
                    user_prompt="hello",
                    reasoning=False,
                    seed=-1,
                    timeout_seconds=10,
                    unload_after_run=True,
                )

        self.assertEqual(str(ctx.exception), "chat failed")
        mock_unload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
