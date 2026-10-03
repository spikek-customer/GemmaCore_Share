#!/usr/bin/env python3
"""Example 3: 100% Offline RAG (Qdrant Edge + LiteRT-LM).

Demonstrates indexing in-memory/local vector chunks and querying without
any external API calls or network connectivity.
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.engine import InferenceEngine, BackendType
from src.rag.store import LocalVectorStore
from src.rag.pipeline import OfflineRAGPipeline


def main() -> None:
    print("=" * 60)
    print("Example 3: 100% Offline RAG Pipeline (Qdrant + LiteRT-LM)")
    print("=" * 60)

    # Sample internal company knowledge doc
    internal_doc = (
        "【社内ナレッジ規程】\n"
        "1. LiteRT-LMはGoogle AI Edgeの最新推論スタックであり、オンデバイスLLM推論を高速化する。\n"
        "2. Apple Silicon MacではMetal GPUアクセラレーションにより、MTP（投機的デコード）が併用可能。\n"
        "3. 機密情報を扱うプロジェクトでは、外部APIへの送信を行わず、Qdrantローカルインスタンスと連携した"
        "完全オフラインRAG構成が必須である。\n"
        "4. ハーネス検証にはGoogle ResearchのEnvHarnessを用い、エージェントの決定論的契約テストを行う。"
    )

    # 1. Initialize local vector store (in-memory embedded mode)
    store = LocalVectorStore(collection_name="internal_rules")

    # 2. Initialize Inference Engine
    model_path = "models/gemma-4-12b-it.litertlm"
    use_mock = not os.path.exists(model_path)
    engine = InferenceEngine(model_path=model_path, backend=BackendType.GPU, mock_mode=use_mock)

    # 3. Create RAG Pipeline
    pipeline = OfflineRAGPipeline(engine=engine, store=store)

    # 4. Ingest document
    print("\n--- Ingesting Document into Local Store ---")
    chunk_count = pipeline.ingest_text(internal_doc, source_name="company_rules.md", chunk_size=150)
    print(f"Indexed {chunk_count} chunks into local vector store.")

    # 5. Query RAG
    query = "社内規程におけるLiteRT-LMとオフラインRAGの利用条件は何ですか？"
    print(f"\nUser Query: {query}")
    print("\n--- Retrieving & Generating Answer Offline ---")

    with engine:
        result = pipeline.query(query, top_k=2)
        print(f"\n[Retrieved Context Chunks]:")
        for i, ctx in enumerate(result["retrieved_contexts"]):
            print(f"  ({i+1}) Score: {ctx['score']:.4f} | Text: {ctx['text'][:60]}...")

        print(f"\n[Assistant Answer]:\n{result['answer']}\n")


if __name__ == "__main__":
    main()
