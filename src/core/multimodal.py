"""Multimodal Input Builder Module for LiteRT-LM & GemmaCore Mac.

Constructs unified multimodal contents (text, image, audio) conforming to
LiteRT-LM official specifications.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional


class MultimodalPayload:
    """Mock-compatible representation of multimodal contents."""

    def __init__(self, text: str, image_paths: List[str], audio_paths: List[str]) -> None:
        self.text = text
        self.image_paths = image_paths
        self.audio_paths = audio_paths

    def __repr__(self) -> str:
        return (
            f"MultimodalPayload(text='{self.text[:30]}...', "
            f"images={len(self.image_paths)}, audio={len(self.audio_paths)})"
        )


class MultimodalInputBuilder:
    """Builds LiteRT-LM Contents payloads containing text, images, and audio."""

    @staticmethod
    def build(
        text_prompt: str,
        image_paths: Optional[List[str]] = None,
        audio_paths: Optional[List[str]] = None,
    ) -> Any:
        """Validate media paths and construct LiteRT-LM Contents payload.

        Args:
            text_prompt: The accompanying text instruction or query.
            image_paths: Optional list of file paths to images.
            audio_paths: Optional list of file paths to audio files.

        Returns:
            litert_lm.Contents instance, or MultimodalPayload if running in test environment.

        Raises:
            FileNotFoundError: If any of the specified media files do not exist.
        """
        valid_images: List[str] = []
        valid_audios: List[str] = []

        if image_paths:
            for img in image_paths:
                abs_path = os.path.abspath(img)
                if not os.path.exists(abs_path):
                    raise FileNotFoundError(f"Multimodal image file does not exist: {img}")
                valid_images.append(abs_path)

        if audio_paths:
            for aud in audio_paths:
                abs_path = os.path.abspath(aud)
                if not os.path.exists(abs_path):
                    raise FileNotFoundError(f"Multimodal audio file does not exist: {aud}")
                valid_audios.append(abs_path)

        # Attempt to build official LiteRT-LM Contents object
        try:
            import litert_lm

            contents_list: List[Any] = [text_prompt]
            for img_path in valid_images:
                contents_list.append(litert_lm.Content.ImageFile(absolute_path=img_path))
            for aud_path in valid_audios:
                contents_list.append(litert_lm.Content.AudioFile(absolute_path=aud_path))

            return litert_lm.Contents.of(*contents_list)
        except (ImportError, AttributeError):
            # Fallback to local MultimodalPayload wrapper
            return MultimodalPayload(
                text=text_prompt,
                image_paths=valid_images,
                audio_paths=valid_audios,
            )
