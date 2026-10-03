"""Unit Tests for Multimodal Input Builder.

Covers TEST-004.
Uses standard library unittest.
"""

import os
import tempfile
import unittest
from src.core.multimodal import MultimodalInputBuilder, MultimodalPayload


class TestMultimodal(unittest.TestCase):

    def test_multimodal_builder_valid_file(self) -> None:
        """TEST-004: Verify valid media file path produces payload."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"dummy image bytes")
            temp_image = f.name

        try:
            payload = MultimodalInputBuilder.build(
                text_prompt="Inspect this UI image",
                image_paths=[temp_image],
            )
            self.assertIsNotNone(payload)
            if isinstance(payload, MultimodalPayload):
                self.assertEqual(payload.text, "Inspect this UI image")
                self.assertEqual(len(payload.image_paths), 1)
        finally:
            if os.path.exists(temp_image):
                os.remove(temp_image)

    def test_multimodal_builder_missing_file_raises_error(self) -> None:
        """TEST-004: Verify missing media file raises FileNotFoundError immediately."""
        with self.assertRaises(FileNotFoundError):
            MultimodalInputBuilder.build(
                text_prompt="Query",
                image_paths=["/path/to/non_existent_image_12345.png"],
            )


if __name__ == "__main__":
    unittest.main()
