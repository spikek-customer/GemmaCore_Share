#!/usr/bin/env python3
"""Example 2: Multimodal Input (Vision & Audio).

Demonstrates unified multimodal content preparation and inference
using LiteRT-LM Contents specification on macOS.
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.engine import InferenceEngine, BackendType
from src.core.multimodal import MultimodalInputBuilder


def main() -> None:
    print("=" * 60)
    print("Example 2: Multimodal Input (Image & Text Analysis)")
    print("=" * 60)

    model_path = "models/gemma-4-12b-multimodal.litertlm"
    use_mock = not os.path.exists(model_path)
    if use_mock:
        print(f"[Notice] Model weight not found at '{model_path}'. Running in verification mock mode.")

    # Create dummy sample screen image if not exists
    sample_image = os.path.join(os.path.dirname(__file__), "sample_screen.png")
    if not os.path.exists(sample_image):
        with open(sample_image, "wb") as f:
            # Minimal 1x1 dummy PNG header bytes
            f.write(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
                b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        print(f"Generated test sample image at: {sample_image}")

    # Build multimodal content payload
    prompt_text = "この画像に写っているUI構成の課題を指摘してください。"
    multimodal_content = MultimodalInputBuilder.build(
        text_prompt=prompt_text,
        image_paths=[sample_image],
    )
    print(f"Constructed Multimodal Content: {multimodal_content}")

    # Execute inference
    with InferenceEngine(
        model_path=model_path,
        backend=BackendType.GPU,
        vision_backend=BackendType.GPU,
        audio_backend=BackendType.CPU,
        mock_mode=use_mock,
    ) as engine:
        with engine.create_conversation() as conversation:
            print(f"\nUser: [Image: {sample_image}] + '{prompt_text}'\n")
            response = conversation.send_message(multimodal_content)
            print(f"Assistant: {response}\n")


if __name__ == "__main__":
    main()
