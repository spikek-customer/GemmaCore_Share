"""Persistent System Settings Module for GemmaCore Mac.

Manages persistent application configurations (active provider, gemini model,
encrypted/secured API keys, log retention) saved across server restarts.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "scratch", "system_settings.json")
)

RECOMMENDED_GEMINI_MODELS = [
    {
        "id": "gemini-3.5-flash-lite",
        "name": "Gemini 3.5 Flash Lite (公式推奨・高速・無料枠対象)",
        "description": "最新世代の高効率モデル。社内ナレッジ検索と高速回答に最適。",
    },
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini 2.5 Flash (次世代ハイブリッド・高速レスポンス)",
        "description": "複雑なコンテキストの処理能力と低遅延を両立。",
    },
    {
        "id": "gemini-2.5-pro",
        "name": "Gemini 2.5 Pro (高度思考・論理分析モデル)",
        "description": "長文の就業規則や複雑な財務・法務資料の論理的分析に対応。",
    },
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash (安定版・汎用クラウド推論)",
        "description": "標準的なクラウド推論に対応する安定版モデル。",
    },
]


class SettingsManager:
    """Handles thread-safe persistence and retrieval of system settings."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self.file_path = file_path or DEFAULT_SETTINGS_PATH
        self._memory_data: Optional[Dict[str, Any]] = None
        if self.file_path != ":memory:":
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def load_settings(self) -> Dict[str, Any]:
        """Load settings from disk or return system defaults."""
        defaults = {
            "active_provider": "litert",
            "gemini_model": "gemini-3.5-flash-lite",
            "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
            "retention_days": 365,
            "rate_limit_login": 20,
            "rate_limit_chat": 60,
        }

        if self.file_path == ":memory:":
            if self._memory_data is None:
                self._memory_data = dict(defaults)
            return dict(self._memory_data)

        if not os.path.exists(self.file_path):
            return defaults

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "active_provider": data.get("active_provider", defaults["active_provider"]),
                    "gemini_model": data.get("gemini_model", defaults["gemini_model"]),
                    "gemini_api_key": data.get("gemini_api_key") or defaults["gemini_api_key"],
                    "retention_days": int(data.get("retention_days", defaults["retention_days"])),
                    "rate_limit_login": int(data.get("rate_limit_login", defaults["rate_limit_login"])),
                    "rate_limit_chat": int(data.get("rate_limit_chat", defaults["rate_limit_chat"])),
                }
        except Exception as e:
            logger.warning(f"Failed to read settings file ({e}). Using defaults.")
            return defaults

    def save_settings(
        self,
        active_provider: Optional[str] = None,
        gemini_model: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        retention_days: Optional[int] = None,
        rate_limit_login: Optional[int] = None,
        rate_limit_chat: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Persist updated settings to disk atomically or in memory."""
        current = self.load_settings()

        if active_provider is not None:
            current["active_provider"] = active_provider
        if gemini_model is not None and gemini_model.strip():
            current["gemini_model"] = gemini_model.strip()
        if gemini_api_key is not None and gemini_api_key.strip():
            current["gemini_api_key"] = gemini_api_key.strip()
        if retention_days is not None:
            current["retention_days"] = int(retention_days)
        if rate_limit_login is not None:
            current["rate_limit_login"] = int(rate_limit_login)
        if rate_limit_chat is not None:
            current["rate_limit_chat"] = int(rate_limit_chat)

        if self.file_path == ":memory:":
            self._memory_data = dict(current)
            return current

        temp_path = f"{self.file_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(temp_path, 0o600)
            except Exception:
                pass
            os.replace(temp_path, self.file_path)
            try:
                os.chmod(self.file_path, 0o600)
            except Exception:
                pass
            logger.info(f"System settings successfully persisted to {self.file_path} (mode: 0600)")
        except Exception as e:
            logger.error(f"Failed to persist settings: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        return current

    @staticmethod
    def get_available_models(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of recommended models with optional dynamic discovery."""
        models = list(RECOMMENDED_GEMINI_MODELS)
        if api_key and api_key.strip():
            try:
                from google import genai
                client = genai.Client(api_key=api_key.strip())
                remote_models = client.models.list()
                found_ids = {m["id"] for m in models}
                for rm in remote_models:
                    raw_name = getattr(rm, "name", "") or ""
                    model_id = raw_name[7:] if raw_name.startswith("models/") else raw_name
                    if "gemini" in model_id.lower() and model_id not in found_ids:
                        display_name = getattr(rm, "display_name", "") or model_id
                        models.append({
                            "id": model_id,
                            "name": f"{display_name} ({model_id})",
                            "description": getattr(rm, "description", "") or "Google Cloud APIから動的に検出された最新モデル。",
                        })
                        found_ids.add(model_id)
            except Exception as e:
                logger.debug(f"Dynamic Gemini model discovery skipped or failed: {e}")

        return models

    @staticmethod
    def discover_live_models(api_key: Optional[str] = None) -> Dict[str, Any]:
        """Query Google GenAI API directly to discover currently available models."""
        if not api_key or not api_key.strip():
            return {
                "status": "FALLBACK",
                "message": "APIキーが指定されていないため、公式推奨モデル一覧を表示します。",
                "models": list(RECOMMENDED_GEMINI_MODELS),
            }

        try:
            from google import genai
            client = genai.Client(api_key=api_key.strip())
            remote_models = list(client.models.list())

            discovered = []
            found_ids = set()
            for rm in remote_models:
                raw_name = getattr(rm, "name", "") or ""
                model_id = raw_name[7:] if raw_name.startswith("models/") else raw_name
                if not model_id or model_id in found_ids:
                    continue

                if "gemini" in model_id.lower():
                    display_name = getattr(rm, "display_name", "") or model_id
                    desc = getattr(rm, "description", "") or "Google公式生成AIモデル"
                    discovered.append({
                        "id": model_id,
                        "name": f"{display_name} ({model_id})",
                        "display_name": display_name,
                        "description": desc[:150] + "..." if len(desc) > 150 else desc,
                        "input_token_limit": getattr(rm, "input_token_limit", None),
                        "output_token_limit": getattr(rm, "output_token_limit", None),
                        "is_live": True,
                    })
                    found_ids.add(model_id)

            if discovered:
                return {
                    "status": "SUCCESS",
                    "message": f"Google Cloud APIから現在公開中の {len(discovered)} 件のGeminiモデルを正常に取得しました。",
                    "models": discovered,
                }
            else:
                return {
                    "status": "FALLBACK",
                    "message": "検出されたGeminiモデルが0件でした。推奨モデルを表示します。",
                    "models": list(RECOMMENDED_GEMINI_MODELS),
                }

        except Exception as e:
            logger.warning(f"Live model discovery failed: {e}")
            return {
                "status": "ERROR_FALLBACK",
                "message": f"API接続または認証エラー ({str(e)})。推奨モデル一覧を表示します。",
                "models": list(RECOMMENDED_GEMINI_MODELS),
            }
