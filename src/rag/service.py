"""Knowledge CMS Service Module.

Provides business logic for document ingestion, sentence-aware chunking,
block-level CRUD, search simulation, and citation formatting.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.rag.chunking import chunk_text_sentence_aware
from src.rag.parser import DocumentParseResult, UniversalDocumentParser
from src.rag.store import LocalVectorStore

logger = logging.getLogger(__name__)


class KnowledgeCMSService:
    """Manages the full lifecycle of company knowledge documents and blocks."""

    def __init__(self, store: Optional[LocalVectorStore] = None) -> None:
        self.store = store or LocalVectorStore()

    def ingest_file(
        self,
        filename: str,
        file_bytes: bytes,
        document_id: Optional[str] = None,
        chunk_size: int = 500,
        overlap: int = 80,
    ) -> Dict[str, Any]:
        """Parse any document format (PDF, Word, Excel, PPT, TXT) and ingest into vector store."""
        parsed = UniversalDocumentParser.parse_file(filename=filename, file_bytes=file_bytes)
        doc_id = document_id or f"doc_{uuid4().hex[:12]}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        all_created_blocks: List[Dict[str, Any]] = []

        for sec in parsed.sections:
            if not sec.text.strip():
                continue
            # Chunk each section with sentence-aware splitting
            chunks = chunk_text_sentence_aware(
                text=sec.text,
                chunk_size=chunk_size,
                overlap=overlap,
                locator=sec.locator,
                heading=filename,
            )

            for draft in chunks:
                block_id = f"blk_{uuid4().hex[:12]}"
                locator_str = f"{sec.locator} (ブロック #{draft.ordinal + 1})" if len(chunks) > 1 else sec.locator

                meta = {
                    "created_at": now_str,
                    "updated_at": now_str,
                    "file_type": parsed.file_type,
                    "original_filename": filename,
                    "section_index": sec.section_index,
                }
                meta.update(sec.metadata)

                self.store.add_or_update_block(
                    block_id=block_id,
                    text=draft.text,
                    document_id=doc_id,
                    document_title=filename,
                    locator=locator_str,
                    metadata=meta,
                )
                all_created_blocks.append({
                    "block_id": block_id,
                    "document_id": doc_id,
                    "document_title": filename,
                    "locator": locator_str,
                    "text": draft.text,
                })

        logger.info(
            f"Ingested {parsed.file_type} file '{filename}' ({doc_id}): "
            f"{len(parsed.sections)} sections, {parsed.total_characters} chars -> {len(all_created_blocks)} blocks."
        )

        return {
            "status": "SUCCESS",
            "document_id": doc_id,
            "filename": filename,
            "file_type": parsed.file_type,
            "total_characters": parsed.total_characters,
            "section_count": len(parsed.sections),
            "indexed_blocks": len(all_created_blocks),
            "blocks": all_created_blocks,
        }

    def ingest_document(
        self,
        title: str,
        text_content: str,
        document_id: Optional[str] = None,
        chunk_size: int = 500,
        overlap: int = 80,
    ) -> List[Dict[str, Any]]:
        """Chunk document using sentence-aware splitting and register blocks."""
        doc_id = document_id or f"doc_{uuid4().hex[:12]}"
        clean_title = title.strip() or "社内資料"

        chunks = chunk_text_sentence_aware(
            text=text_content,
            chunk_size=chunk_size,
            overlap=overlap,
            locator="",
            heading=clean_title,
        )

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        created_blocks: List[Dict[str, Any]] = []

        for draft in chunks:
            block_id = f"blk_{uuid4().hex[:12]}"
            locator_str = f"{clean_title} (ブロック #{draft.ordinal + 1})"
            self.store.add_or_update_block(
                block_id=block_id,
                text=draft.text,
                document_id=doc_id,
                document_title=clean_title,
                locator=locator_str,
                metadata={
                    "created_at": now_str,
                    "updated_at": now_str,
                    "ordinal": draft.ordinal,
                    "start_offset": draft.start_offset,
                    "end_offset": draft.end_offset,
                },
            )
            created_blocks.append({
                "block_id": block_id,
                "document_id": doc_id,
                "document_title": clean_title,
                "locator": locator_str,
                "text": draft.text,
            })

        logger.info(f"Ingested document '{clean_title}' ({doc_id}) into {len(chunks)} blocks.")
        return created_blocks

    def add_single_block(
        self,
        document_title: str,
        text: str,
        locator: str = "",
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Manually add a single knowledge text block."""
        block_id = f"blk_{uuid4().hex[:12]}"
        doc_id = document_id or f"doc_{uuid4().hex[:12]}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.store.add_or_update_block(
            block_id=block_id,
            text=text,
            document_id=doc_id,
            document_title=document_title,
            locator=locator or f"{document_title} (追記)",
            metadata={"created_at": now_str, "updated_at": now_str},
        )
        return self.store.get_block(block_id) or {}

    def update_block_text(self, block_id: str, new_text: str) -> Dict[str, Any]:
        """Update a specific block's text and re-index immediately."""
        existing = self.store.get_block(block_id)
        if not existing:
            raise KeyError(f"Block with ID '{block_id}' does not exist.")

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.store.add_or_update_block(
            block_id=block_id,
            text=new_text,
            document_id=existing.get("document_id", ""),
            document_title=existing.get("document_title", ""),
            locator=existing.get("locator", ""),
            metadata={**existing.get("metadata", {}), "updated_at": now_str},
        )
        logger.info(f"Block '{block_id}' successfully updated and re-indexed.")
        return self.store.get_block(block_id) or {}

    def delete_block(self, block_id: str) -> bool:
        """Delete a block from index."""
        return self.store.delete_block(block_id)

    def delete_document(self, document_id: str) -> int:
        """Delete all blocks belonging to a specific document."""
        return self.store.delete_document_blocks(document_id)

    def list_blocks(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """List blocks filtered by keyword."""
        return self.store.list_blocks(query=query)

    def search_fast(
        self,
        query: str,
        limit: int = 5,
        expanded_keywords: Optional[List[str]] = None,
        user_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fast retrieval (< 1s) skipping intermediate LLM generation.

        Returns matching blocks, clean citation links, and formatted context block.
        """
        hits = self.store.search(
            query=query,
            top_k=limit,
            expanded_keywords=expanded_keywords,
            user_role=user_role,
        )
        citations = []
        unique_titles = []

        context_blocks = []
        for i, hit in enumerate(hits):
            title = hit.get("document_title", "社内資料")
            locator = hit.get("locator", f"ブロック #{i+1}")
            text = hit.get("text", "")
            citations.append({
                "id": f"S{i+1}",
                "block_id": hit.get("block_id"),
                "document_title": title,
                "locator": locator,
                "score": hit.get("score", 0.0),
                "text": text,
            })
            if title not in unique_titles:
                unique_titles.append(title)
            context_blocks.append(f"[{i+1}] 【{title} / {locator}】:\n{text}")

        # MuseGlimmer-style clean 1-line markdown citations
        citation_links = [f"[{t}](internal://knowledge/{t})" for t in unique_titles]

        return {
            "query": query,
            "expanded_keywords": expanded_keywords or [],
            "hit_count": len(hits),
            "citations": citations,
            "citation_links": citation_links,
            "context_text": "\n\n".join(context_blocks),
        }
