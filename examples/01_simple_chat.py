#!/usr/bin/env python3
"""Example 1: Basic Text Inference & Multi-turn Conversation Loop.

Demonstrates official LiteRT-LM Engine context manager, system prompt configuration,
and multi-turn conversation on macOS Apple Silicon.
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.engine import InferenceEngine, BackendType


def main() -> None:
    print("=" * 60)
    print("Example 1: Basic Text Inference & Multi-turn Conversation")
    print("=" * 60)

    model_path = "models/gemma-4-12b-it.litertlm"
    # Use mock_mode=True if model weights are not yet downloaded locally
    use_mock = not os.path.exists(model_path)
    if use_mock:
        print(f"[Notice] Model weight not found at '{model_path}'. Running in verification mock mode.")

    # 1. Initialize Engine with Metal GPU backend and Speculative Decoding (MTP)
    with InferenceEngine(
        model_path=model_path,
        backend=BackendType.GPU,
        enable_speculative_decoding=True,
        mock_mode=use_mock,
    ) as engine:
        print(f"Active Backend: {engine.active_backend}")

        # 2. Create stateful conversation with system persona
        system_instruction = "あなたは優秀で論理的なローカルAIアシスタントです。"
        with engine.create_conversation(system_prompt=system_instruction) as conversation:
            user_input = "LiteRT-LMの特徴と従来のTFLiteとの違いは何ですか？"
            print(f"\nUser: {user_input}\n")

            # 3. Send message and receive response
            answer = conversation.send_message(user_input)
            print(f"Assistant: {answer}\n")

            # Multi-turn continuation
            follow_up = "Apple Siliconでの推論高速化にはどのような工夫がありますか？"
            print(f"User: {follow_up}\n")
            follow_up_answer = conversation.send_message(follow_up)
            print(f"Assistant: {follow_up_answer}\n")

    print("Engine closed safely. Resources released.")


if __name__ == "__main__":
    main()
