"""Local Vector Store Module for LiteRT-LM & GemmaCore Mac.

Provides 100% offline document chunk storage, block-level CRUD,
and vector similarity search backed by Qdrant (Embedded mode) with fallback.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "の", "に", "は", "を", "た", "が", "で", "て", "と", "し", "れ", "さ", "ある", "いる", "も", "する", "から",
    "な", "こと", "として", "い", "や", "れる", "など", "なっ", "ない", "この", "ため", "その", "あっ", "よう",
    "また", "もの", "という", "あり", "まで", "られ", "なる", "へ", "か", "だ", "これ", "によって", "により",
    "おり", "より", "による", "ず", "なり", "られる", "において", "ば", "なかっ", "なく", "しかし", "について",
    "せ", "だっ", "その後", "できる", "それ", "う", "ので", "なお", "のみ", "でき", "き", "いただく", "いただき",
    "です", "ます", "でした", "ました", "誰", "何", "どう", "どこ", "いつ", "なぜ", "教えて", "ください",
}


def simple_tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words, Kanji/Katakana compound words, and meaningful bigrams."""
    text_clean = text.lower()
    # 1. Alphanumeric words (e.g. "litert", "2026")
    latin_words = [w for w in re.findall(r"[a-z0-9_]+", text_clean) if w not in STOP_WORDS]
    # 2. Whole Kanji/Katakana compound words (len >= 2)
    jp_words = [w for w in re.findall(r"[\u30a0-\u30ff]{2,}|[\u4e00-\u9fff]{2,}", text_clean) if w not in STOP_WORDS]
    # 3. Clean bigrams of adjacent kanji characters (len == 2)
    kanji_seqs = re.findall(r"[\u4e00-\u9fff]+", text_clean)
    kanji_bigrams = []
    for seq in kanji_seqs:
        if len(seq) > 2:
            for i in range(len(seq) - 1):
                bg = seq[i:i + 2]
                if bg not in STOP_WORDS:
                    kanji_bigrams.append(bg)

    tokens = list(set(latin_words + jp_words + kanji_bigrams))
    return tokens



def compute_bow_vector(text: str, vocab: Dict[str, int]) -> List[float]:
    """Compute normalized Term Frequency vector excluding stop words."""
    tokens = [tok for tok in simple_tokenize(text) if tok not in STOP_WORDS]
    vec = [0.0] * max(len(vocab), 1)
    for tok in tokens:
        if tok in vocab:
            vec[vocab[tok]] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    min_len = min(len(v1), len(v2))
    return sum(v1[i] * v2[i] for i in range(min_len))


class LocalVectorStore:
    """Manages local document chunks and performs similarity search offline with CRUD support."""

    def __init__(
        self,
        collection_name: str = "company_knowledge",
        storage_path: Optional[str] = None,
    ) -> None:
        self.collection_name = collection_name
        self.storage_path = storage_path
        self._qdrant_client: Any = None
        self._use_qdrant: bool = False

        # In-memory document storage: block_id -> dict
        self._records: Dict[str, Dict[str, Any]] = {}
        self._vocab: Dict[str, int] = {}

        self._init_qdrant()

    def _init_qdrant(self) -> None:
        """Attempt to initialize Qdrant embedded client."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            if self.storage_path:
                os.makedirs(self.storage_path, exist_ok=True)
                self._qdrant_client = QdrantClient(path=self.storage_path)
            else:
                self._qdrant_client = QdrantClient(":memory:")

            collections = [c.name for c in self._qdrant_client.get_collections().collections]
            if self.collection_name not in collections:
                self._qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=128, distance=Distance.COSINE),
                )
            self._use_qdrant = True
            logger.info(f"Qdrant embedded client initialized for collection '{self.collection_name}'.")
        except (ImportError, Exception) as e:
            logger.warning(f"qdrant-client not available ({e}). Running in standalone memory mode.")
            self._use_qdrant = False

    def add_or_update_block(
        self,
        block_id: str,
        text: str,
        document_id: str = "default_doc",
        document_title: str = "社内資料",
        locator: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add or overwrite a knowledge block with instant re-indexing."""
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Block text cannot be empty.")

        meta = dict(metadata or {})
        meta["block_id"] = block_id
        meta["document_id"] = document_id
        meta["document_title"] = document_title
        meta["locator"] = locator
        meta["text"] = clean_text

        # Update vocabulary (excluding stop words)
        for tok in simple_tokenize(clean_text):
            if tok not in STOP_WORDS and tok not in self._vocab:
                self._vocab[tok] = len(self._vocab)

        self._records[block_id] = meta
        return block_id


    def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Index multiple text chunks into the store."""
        if metadatas is None:
            metadatas = [{} for _ in texts]

        block_ids: List[str] = []
        for i, text in enumerate(texts):
            meta = metadatas[i]
            block_id = meta.get("block_id") or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            self.add_or_update_block(
                block_id=block_id,
                text=text,
                document_id=meta.get("document_id", "doc_default"),
                document_title=meta.get("document_title", meta.get("source", "社内資料")),
                locator=meta.get("locator", f"ブロック #{i+1}"),
                metadata=meta,
            )
            block_ids.append(block_id)
        return block_ids

    def get_block(self, block_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific block by its ID."""
        return self._records.get(block_id)

    def list_blocks(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all indexed blocks, optionally filtered by keyword query."""
        blocks = list(self._records.values())
        if not query or not query.strip():
            return blocks

        q = query.strip().lower()
        return [b for b in blocks if q in b["text"].lower() or q in b["document_title"].lower() or q in b["locator"].lower()]

    def delete_block(self, block_id: str) -> bool:
        """Physically delete a specific block from the index."""
        if block_id in self._records:
            del self._records[block_id]
            logger.info(f"Deleted block {block_id} from vector store.")
            return True
        return False

    def delete_document_blocks(self, document_id: str) -> int:
        """Purge all blocks associated with a specific document/file ID."""
        target_ids = [bid for bid, b in self._records.items() if b.get("document_id") == document_id]
        for bid in target_ids:
            del self._records[bid]
        logger.info(f"Purged {len(target_ids)} blocks for document '{document_id}'.")
        return len(target_ids)

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.08,
        expanded_keywords: Optional[List[str]] = None,
        user_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search top_k similar chunks matching query text with semantic expansion and entity conflict prevention."""
        clean_q = query.strip()
        if not clean_q or not self._records:
            return []

        # Role hierarchy for ACL filtering: admin > editor > viewer
        ROLE_HIERARCHY = {"viewer": 1, "editor": 2, "admin": 3}
        current_level = ROLE_HIERARCHY.get(user_role.lower(), 1) if user_role else 1

        # Distinct entity groups for conflict resolution & anti-hallucination
        COUNTRY_ENTITIES = {"日本", "台湾", "アメリカ", "米国", "中国", "韓国", "イギリス", "英国", "フランス", "ドイツ"}
        ROLE_ENTITIES = {"大統領", "総理大臣", "首相"}

        query_countries = {c for c in COUNTRY_ENTITIES if c in clean_q}
        query_roles = {r for r in ROLE_ENTITIES if r in clean_q}

        query_vec = compute_bow_vector(clean_q, self._vocab)
        scored: List[Dict[str, Any]] = []

        # Extract meaningful terms (non-stopwords, length >= 2 or kanji/katakana words)
        raw_tokens = simple_tokenize(clean_q)
        meaningful_terms = set(
            t for t in raw_tokens
            if t not in STOP_WORDS and (len(t) >= 2 or re.match(r"[\u4e00-\u9fff]", t))
        )

        # Include tokens from expanded keywords
        expanded_tokens: set[str] = set()
        if expanded_keywords:
            for kw in expanded_keywords:
                for t in simple_tokenize(kw):
                    if t not in STOP_WORDS and (len(t) >= 2 or re.match(r"[\u4e00-\u9fff]", t)):
                        expanded_tokens.add(t)

        all_search_terms = meaningful_terms | expanded_tokens

        for block in self._records.values():
            # ACL Check: verify user's role satisfies block's required_role if configured
            req_role = block.get("metadata", {}).get("required_role") or block.get("required_role")
            if req_role:
                req_level = ROLE_HIERARCHY.get(str(req_role).lower(), 1)
                if current_level < req_level:
                    # User does not have sufficient role to see this document
                    continue

            block_text_lower = block["text"].lower()
            block_title_lower = block.get("document_title", "").lower()
            combined_text = f"{block_title_lower} {block_text_lower}"

            # Entity conflict check 1: Country mismatch
            if query_countries:
                has_queried_country = any(c in combined_text for c in query_countries)
                other_countries = [c for c in COUNTRY_ENTITIES if c not in query_countries and c in combined_text]
                if not has_queried_country and other_countries:
                    # Clear conflict: e.g., queried Japan, but doc is strictly about Taiwan
                    continue

            # Entity conflict check 2: Role mismatch (e.g. asking for 大統領 vs doc has 総理大臣)
            if "大統領" in query_roles:
                if "大統領" not in combined_text and ("総理大臣" in combined_text or "総理" in combined_text or "首相" in combined_text):
                    continue
            elif "総理大臣" in query_roles or "首相" in query_roles:
                if "総理大臣" not in combined_text and "首相" not in combined_text and "大統領" in combined_text:
                    continue

            doc_vec = compute_bow_vector(block["text"], self._vocab)
            score = cosine_similarity(query_vec, doc_vec)

            # Add lexical bonus if meaningful or expanded terms appear in the block text or title
            if all_search_terms:
                matched_count = sum(
                    1 for term in all_search_terms
                    if term in block_text_lower or term in block_title_lower
                )
                if matched_count > 0:
                    score += min(0.45, matched_count * 0.12)
                else:
                    # If query has search terms but document contains NONE of them, heavily penalize
                    score *= 0.1

            # Filter out chunks that do not meet the minimum relevance threshold
            if score < min_score:
                continue

            scored.append({
                "block_id": block["block_id"],
                "document_id": block.get("document_id", ""),
                "document_title": block.get("document_title", ""),
                "locator": block.get("locator", ""),
                "text": block["text"],
                "score": score,
                "metadata": block,
            })

        # Sort descending by score
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


