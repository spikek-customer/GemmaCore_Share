"""Offline & Hybrid RAG Pipeline Module for LiteRT-LM & GemmaCore Mac.

Combines local document indexing, sentence-aware chunking, similarity search,
fast retrieval (< 1s), and local/cloud LLM inference with clean citations.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.rag.query_expander import QueryExpander
from src.rag.service import KnowledgeCMSService
from src.rag.store import LocalVectorStore

if TYPE_CHECKING:
    from src.core.engine import InferenceEngine

logger = logging.getLogger(__name__)


class OfflineRAGPipeline:
    """End-to-end RAG orchestrator with fast search and clean citation generation."""

    def __init__(
        self,
        engine: "InferenceEngine",
        store: Optional[LocalVectorStore] = None,
        service: Optional[KnowledgeCMSService] = None,
        expander: Optional[QueryExpander] = None,
    ) -> None:
        self.engine = engine
        self.store = store or LocalVectorStore()
        self.cms = service or KnowledgeCMSService(store=self.store)
        self.expander = expander or QueryExpander(engine=self.engine)

    def ingest_text(
        self,
        text: str,
        source_name: str = "社内資料",
        chunk_size: int = 500,
        overlap: int = 80,
    ) -> int:
        """Ingest text using sentence-aware boundary preservation."""
        blocks = self.cms.ingest_document(
            title=source_name,
            text_content=text,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        return len(blocks)

    def ingest_file(self, file_path: str, chunk_size: int = 500, overlap: int = 80) -> int:
        """Read and index a local file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Target document file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return self.ingest_text(
            text=content,
            source_name=os.path.basename(file_path),
            chunk_size=chunk_size,
            overlap=overlap,
        )

    def search_only(
        self,
        question: str,
        top_k: int = 5,
        expand_query: bool = True,
        user_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fast retrieval (< 1s) with optional LLM semantic query expansion and ACL check."""
        expanded_keywords: List[str] = []
        understanding: Dict[str, Any] = {}
        if expand_query and self.expander:
            understanding = self.expander.expand(question)
            expanded_keywords = understanding.get("all_keywords", [])

        res = self.cms.search_fast(
            query=question,
            limit=top_k,
            expanded_keywords=expanded_keywords,
            user_role=user_role,
        )
        res["query_understanding"] = understanding
        return res

    def query(self, question: str, top_k: int = 3, user_role: Optional[str] = None) -> Dict[str, Any]:
        """Perform query understanding, context retrieval, and hybrid LLM answer generation."""
        import re

        fast_res = self.search_only(question, top_k=top_k, expand_query=True, user_role=user_role)
        context_str = fast_res["context_text"] or "（関連する社内資料は見つかりませんでした）"

        # Construct prompt enforcing facts, strict entity matching, and clean citation
        rag_prompt = (
            "あなたは社内専用AIアシスタントです。以下の【社内ナレッジ検索結果】に記載された事実のみに基づき、質問に正確・誠実に回答してください。\n\n"
            "【厳格な遵守ルール】\n"
            "1. 質問で問われている『対象（国名・地域名・制度名・人物・役職・組織など）』と、検索結果に書かれている『対象』が完全に一致しているかを必ず確認してください。\n"
            "2. 質問の対象（例: 日本、大統領など）に関する情報が検索結果に存在しない場合、検索結果に含まれる別の対象や役職（例: 台湾、総理大臣など）の情報を勝手に当てはめて回答することは重大な誤情報となるため厳禁です。\n"
            "3. 質問された対象についての具体的な事実が社内ナレッジにない場合は、必ず『社内ナレッジには、○○に関する記載はありません。』とだけ明確に回答してください。関係のない別の対象や役職（例: 台湾、総理大臣など）の情報を勝手に補足・案内・推測することは厳禁です。\n"
            "4. 質問への回答として不要なナレッジの引用や補足説明、一般的な世間話は一切行わないでください。\n"
            "5. 本文中に『[1]』等の内部記号は含めず、自然で丁寧な日本語で回答してください。\n\n"
            f"【社内ナレッジ検索結果】\n{context_str}\n\n"
            f"【質問】\n{question}\n\n"
            "【回答】"
        )

        answer = self.engine.generate(rag_prompt)

        # Check if the answer indicates negative / missing information in knowledge
        negative_indicators = [
            "記載はありません", "記載がありません", "記載は見当たりません",
            "見つかりませんでした", "含まれていません", "登録されていません",
            "情報はありません", "規定はありません", "該当する情報はありません",
            "関連する社内資料は見つかりませんでした",
        ]
        is_missing_info = any(neg in answer for neg in negative_indicators) or (
            "（関連する社内資料は見つかりませんでした）" in context_str
        )

        citation_links = list(fast_res["citation_links"])
        retrieved_contexts = list(fast_res["citations"])

        if is_missing_info:
            # Strictly suppress citation links and references when knowledge does not contain the answer
            citation_links = []
            retrieved_contexts = []
            # Strip any hallucinated citation text or unsolicited notes that might have been emitted
            answer = re.sub(r"\n*📎\s*\*?参照:[^\n]*", "", answer).strip()
            answer = re.sub(r"\n*なお、社内ナレッジには[^\n]*", "", answer).strip()
            answer = re.sub(r"（※参考:[^）]*）", "", answer).strip()
        elif citation_links and "関連する社内資料は見つかりませんでした" not in context_str:
            # Cleanly append 1-line citation
            first_link = citation_links[0]
            if f"📎 *参照: {first_link}*" not in answer:
                answer = f"{answer.strip()}\n\n📎 *参照: {first_link}*"

        return {
            "question": question,
            "answer": answer,
            "query_understanding": fast_res.get("query_understanding", {}),
            "retrieved_contexts": retrieved_contexts,
            "citation_links": citation_links,
            "full_prompt": rag_prompt,
        }


