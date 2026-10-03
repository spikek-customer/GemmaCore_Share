"""Inference Engine Module for LiteRT-LM & GemmaCore Mac.

Supports Hybrid Inference:
1. Local On-Device: Google LiteRT-LM (Metal GPU / XNNPACK CPU)
2. Cloud API: Google GenAI SDK (Gemini 2.0 Flash / Pro)
"""

from __future__ import annotations

import gc
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from src.core.gemini_provider import GeminiCloudProvider

logger = logging.getLogger(__name__)


class BackendType(str, Enum):
    """Supported local inference backends."""
    GPU = "gpu"
    CPU = "cpu"
    NPU = "npu"


class ProviderType(str, Enum):
    """Supported inference providers."""
    LITERT = "litert"
    GEMINI = "gemini"


class InferenceEngine:
    """Manages LiteRT-LM runtime and cloud Gemini API under a unified interface."""

    def __init__(
        self,
        model_path: str = "models/gemma-4-12b-it.litertlm",
        provider: Union[str, ProviderType] = ProviderType.LITERT,
        backend: Union[str, BackendType] = BackendType.GPU,
        enable_speculative_decoding: bool = True,
        vision_backend: Optional[Union[str, BackendType]] = None,
        audio_backend: Optional[Union[str, BackendType]] = None,
        cache_dir: Optional[str] = None,
        fallback_to_cpu: bool = True,
        mock_mode: bool = False,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-3.5-flash-lite",
    ) -> None:
        self.model_path = model_path
        self.provider = ProviderType(provider) if isinstance(provider, str) else provider
        self.requested_backend = BackendType(backend) if isinstance(backend, str) else backend
        self.enable_speculative_decoding = enable_speculative_decoding
        self.vision_backend = vision_backend
        self.audio_backend = audio_backend
        self.cache_dir = cache_dir
        self.fallback_to_cpu = fallback_to_cpu
        self.mock_mode = mock_mode

        # Cloud Gemini Provider
        self.gemini_provider = GeminiCloudProvider(
            api_key=gemini_api_key,
            model_name=gemini_model,
        )

        self.active_backend: Optional[BackendType] = None
        self._raw_engine: Any = None
        self._is_closed: bool = False

    def __enter__(self) -> "InferenceEngine":
        self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def initialize(self) -> None:
        """Initialize LiteRT-LM Engine or Cloud Gemini connection."""
        if self.provider == ProviderType.GEMINI:
            logger.info("Operating in Cloud Gemini API mode.")
            return

        if self._raw_engine is not None or self.mock_mode:
            if self.mock_mode:
                self.active_backend = self.requested_backend
                logger.info(f"Initialized LiteRT-LM in MOCK mode with backend: {self.active_backend}")
            return

        if not os.path.exists(self.model_path):
            logger.info(f"Local model weight not found at {self.model_path}. Running in mock mode.")
            self.mock_mode = True
            self.active_backend = self.requested_backend
            return

        try:
            import litert_lm
        except ImportError:
            logger.warning("litert_lm package is not installed. Falling back to mock mode.")
            self.mock_mode = True
            self.active_backend = self.requested_backend
            return

        backend_obj = self._resolve_backend_object(litert_lm, self.requested_backend)
        try:
            logger.info(f"Initializing LiteRT-LM Engine with backend: {self.requested_backend}")
            self._raw_engine = litert_lm.Engine(
                self.model_path,
                backend=backend_obj,
                enable_speculative_decoding=self.enable_speculative_decoding,
                cache_dir=self.cache_dir,
            )
            self.active_backend = self.requested_backend
        except Exception as e:
            if self.fallback_to_cpu and self.requested_backend != BackendType.CPU:
                logger.warning(
                    f"GPU/Backend initialization failed: {e}. Falling back to CPU backend."
                )
                cpu_backend = self._resolve_backend_object(litert_lm, BackendType.CPU)
                self._raw_engine = litert_lm.Engine(
                    self.model_path,
                    backend=cpu_backend,
                    enable_speculative_decoding=False,
                    cache_dir=self.cache_dir,
                )
                self.active_backend = BackendType.CPU
            else:
                raise

    def _resolve_backend_object(self, litert_lm_module: Any, backend_type: BackendType) -> Any:
        if backend_type == BackendType.GPU:
            return litert_lm_module.Backend.GPU()
        elif backend_type == BackendType.NPU:
            return litert_lm_module.Backend.NPU()
        else:
            return litert_lm_module.Backend.CPU()

    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> "ConversationSession":
        from src.core.conversation import ConversationSession

        raw_conv = None
        if self.provider == ProviderType.LITERT and not self.mock_mode and self._raw_engine is not None:
            import litert_lm

            initial_messages = []
            if system_prompt:
                initial_messages.append(litert_lm.Message.system(system_prompt))
            if messages:
                for m in messages:
                    role = m.get("role", "user")
                    text = m.get("content", "")
                    if role == "user":
                        initial_messages.append(litert_lm.Message.user(text))
                    elif role == "assistant":
                        initial_messages.append(litert_lm.Message.assistant(text))

            raw_conv = self._raw_engine.create_conversation(messages=initial_messages)

        return ConversationSession(
            engine=self,
            raw_conversation=raw_conv,
            system_prompt=system_prompt,
            mock_mode=self.mock_mode or (self.provider == ProviderType.GEMINI),
        )

    def generate(self, prompt: str, system_instruction: Optional[str] = None, **kwargs: Any) -> str:
        """One-shot generation dispatching to Cloud Gemini or Local LiteRT-LM."""
        if self.provider == ProviderType.GEMINI:
            return self.gemini_provider.generate(prompt=prompt, system_instruction=system_instruction)

        with self.create_conversation(system_prompt=system_instruction) as conv:
            return conv.send_message(prompt)

    def close(self) -> None:
        if self._is_closed:
            return

        if self._raw_engine is not None:
            if hasattr(self._raw_engine, "close"):
                self._raw_engine.close()
            self._raw_engine = None

        self._is_closed = True
        gc.collect()
        logger.info("InferenceEngine resources safely released.")
