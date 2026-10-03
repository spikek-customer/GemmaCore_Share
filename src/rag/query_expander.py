"""LLM-Assisted Query Understanding & Semantic Expansion Module.

Understands user intent, detects entities, resolves synonyms, and generates
enterprise-ready search terms so that colloquial questions reliably match
formal company regulations and documents.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.core.engine import InferenceEngine

logger = logging.getLogger(__name__)

# Built-in enterprise synonym and semantic expansion dictionary (Zero-dependency fallback)
ENTERPRISE_SYNONYM_MAP: Dict[str, List[str]] = {
    "定期": ["通勤手当", "交通費", "交通系ICカード", "上限額", "定期代"],
    "定期代": ["通勤手当", "交通費", "上限額", "近郊交通費"],
    "電車": ["通勤手当", "交通費", "近郊移動", "交通系ICカード"],
    "交通費": ["通勤手当", "近郊交通費", "交通費精算", "領収書", "当月末日"],
    "バス": ["通勤手当", "交通費", "領収書"],
    "テレワーク": ["在宅リモートワーク", "在宅勤務", "リモートワーク", "週3日"],
    "在宅": ["在宅リモートワーク", "リモートワーク", "週3日"],
    "リモート": ["在宅リモートワーク", "在宅勤務", "リモートワーク"],
    "有給": ["特別休暇", "慶弔特別休暇", "就業規則", "申請基準"],
    "有休": ["特別休暇", "慶弔特別休暇", "就業規則"],
    "休み": ["特別休暇", "慶弔特別休暇", "連続3日", "就業規則"],
    "慶弔": ["慶弔特別休暇", "特別休暇", "連続3日"],
    "結婚": ["慶弔特別休暇", "特別休暇", "連続3日"],
    "出張": ["近郊交通費", "旅費精算", "交通費"],
    "ai": ["AIツールの業務利用基準", "LiteRT-LM", "完全ローカル推論", "クラウドGemini"],
    "人工知能": ["AIツールの業務利用基準", "社内AIアシスタント"],
    "litert": ["LiteRT-LM", "完全ローカル推論", "MTP", "Metal GPU"],
    "gemini": ["クラウドGemini API", "AIツールの業務利用基準"],
}


class QueryExpander:
    """Understands user query intent and expands search queries using LLM or heuristic fallback."""

    def __init__(self, engine: Optional["InferenceEngine"] = None) -> None:
        self.engine = engine

    def expand(self, query: str) -> Dict[str, Any]:
        """Understand query intent and return expanded terms and keywords.

        Args:
            query: The raw user question.

        Returns:
            Dictionary with original query, recognized intent, formal keywords, and expanded terms.
        """
        clean_q = query.strip()
        if not clean_q:
            return {
                "original_query": "",
                "intent": "",
                "formal_terms": [],
                "expanded_queries": [],
                "all_keywords": [],
            }

        # 1. Attempt LLM-based query understanding if engine is provided
        if self.engine is not None:
            try:
                llm_result = self._expand_with_llm(clean_q)
                if llm_result and (llm_result.get("formal_terms") or llm_result.get("expanded_queries")):
                    return llm_result
            except Exception as e:
                logger.warning(f"LLM query expansion failed or timed out ({e}). Falling back to semantic dictionary.")

        # 2. Deterministic heuristic & synonym expansion fallback
        return self._expand_with_heuristics(clean_q)

    def _expand_with_llm(self, query: str) -> Optional[Dict[str, Any]]:
        """Ask LLM to extract intent, formal business terms, and expanded search queries."""
        expansion_prompt = (
            "あなたは社内規程・ナレッジ検索のための【クエリ理解・意図解釈エンジン】です。\n"
            "ユーザーからの質問を深く理解し、社内文書（就業規則、経費ガイドライン、業務マニュアル等）で"
            "使われている正式な業務用語、同義語、表記揺れを補完した検索用キーワードを展開してください。\n\n"
            "【ユーザーの質問】\n"
            f"{query}\n\n"
            "以下のJSON形式のみを出力してください（Markdownコードブロックは不要です）:\n"
            "{\n"
            '  "intent": "ユーザーが知りたい業務上の要約",\n'
            '  "formal_terms": ["社内規程で使われる正式用語1", "正式用語2", ...],\n'
            '  "expanded_queries": ["検索用フレーズ1", "検索用フレーズ2", ...]\n'
            "}"
        )

        raw_output = self.engine.generate(expansion_prompt) if self.engine else ""
        if not raw_output:
            return None

        # Parse JSON from response
        try:
            # Extract JSON block if wrapped in markdown
            json_text = raw_output
            if "```json" in raw_output:
                json_text = raw_output.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_output:
                json_text = raw_output.split("```")[1].split("```")[0].strip()

            data = json.loads(json_text)
            formal_terms = data.get("formal_terms", [])
            expanded_queries = data.get("expanded_queries", [])

            # Merge with heuristic dictionary to guarantee essential coverage
            heuristic_data = self._expand_with_heuristics(query)
            combined_terms = list(dict.fromkeys(formal_terms + heuristic_data["formal_terms"]))
            combined_queries = list(dict.fromkeys(expanded_queries + heuristic_data["expanded_queries"]))

            return {
                "original_query": query,
                "intent": data.get("intent", query),
                "formal_terms": combined_terms,
                "expanded_queries": combined_queries,
                "all_keywords": list(dict.fromkeys([query] + combined_terms + combined_queries)),
            }
        except Exception as e:
            logger.debug(f"Failed to parse LLM query expansion JSON: {e}")
            return None

    def _expand_with_heuristics(self, query: str) -> Dict[str, Any]:
        """Rule-based expansion using built-in enterprise synonym map."""
        q_lower = query.lower()
        formal_terms: List[str] = []
        expanded_queries: List[str] = []

        for trigger_word, synonyms in ENTERPRISE_SYNONYM_MAP.items():
            if trigger_word in q_lower:
                formal_terms.extend(synonyms)
                # Formulate combined search query
                expanded_queries.append(" ".join(synonyms[:2]))

        unique_formal = list(dict.fromkeys(formal_terms))
        unique_expanded = list(dict.fromkeys(expanded_queries))
        all_keywords = list(dict.fromkeys([query] + unique_formal + unique_expanded))

        return {
            "original_query": query,
            "intent": "社内文書検索",
            "formal_terms": unique_formal,
            "expanded_queries": unique_expanded,
            "all_keywords": all_keywords,
        }
