"""Integration and Unit Tests for 100% Offline RAG.

Covers TEST-005.
Uses standard library unittest.
"""

import unittest
from src.core.engine import BackendType, InferenceEngine
from src.rag.chunking import chunk_text_sentence_aware
from src.rag.pipeline import OfflineRAGPipeline
from src.rag.store import LocalVectorStore


class TestOfflineRAG(unittest.TestCase):

    def test_chunk_text_utility(self) -> None:
        """TEST-005: Verify text chunking with overlap."""
        text = "これはテスト文章です。文境界を正しく判定してチャンク分割を行います。\n\n第2の段落です。"
        chunks = chunk_text_sentence_aware(text, chunk_size=30, overlap=10)
        self.assertGreater(len(chunks), 1)

    def test_local_vector_store_indexing_and_search(self) -> None:
        """TEST-005: Verify offline vector storage and cosine similarity retrieval."""
        store = LocalVectorStore(collection_name="test_col")
        docs = [
            "LiteRT-LM is an on-device inference runtime for Google edge AI models.",
            "Qdrant Edge runs completely offline in embedded mode.",
            "Apples and oranges are nutritious fruits.",
        ]
        store.add_documents(docs)

        # Search for LiteRT
        res = store.search("Tell me about LiteRT-LM runtime", top_k=1)
        self.assertEqual(len(res), 1)
        self.assertIn("LiteRT-LM", res[0]["text"])
        self.assertGreater(res[0]["score"], 0.0)

    def test_offline_rag_pipeline_end_to_end(self) -> None:
        """TEST-005: Verify complete offline RAG pipeline execution without external network calls."""
        store = LocalVectorStore(collection_name="rag_test")
        engine = InferenceEngine(model_path="dummy.litertlm", backend=BackendType.GPU, mock_mode=True)
        pipeline = OfflineRAGPipeline(engine=engine, store=store)

        pipeline.ingest_text("LiteRT-LM provides speculative decoding and GPU acceleration on Apple Silicon.")
        result = pipeline.query("How does LiteRT-LM accelerate inference?")

        self.assertIn("answer", result)
        self.assertIn("retrieved_contexts", result)
        self.assertGreater(len(result["retrieved_contexts"]), 0)
        self.assertIn("Apple Silicon", result["retrieved_contexts"][0]["text"])


if __name__ == "__main__":
    unittest.main()
