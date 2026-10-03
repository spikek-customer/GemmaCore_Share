"""Test LLM-Assisted Query Understanding & Expansion (TEST-031).

Verifies that colloquial, indirect, and synonym-heavy questions (e.g. "電車の定期代", "テレワーク")
are first understood and expanded by the LLM into formal business terminology,
reliably retrieving company regulations while strictly maintaining anti-hallucination guards.
"""

from __future__ import annotations

import unittest
from src.core.engine import BackendType, InferenceEngine, ProviderType
from src.rag.pipeline import OfflineRAGPipeline
from src.rag.query_expander import QueryExpander
from src.rag.service import KnowledgeCMSService
from src.rag.store import LocalVectorStore
from src.web.app import KnowledgeWebApp


class TestQueryUnderstandingAndExpansion(unittest.TestCase):
    """TEST-031: LLM-Assisted Query Understanding and Semantic Search Expansion."""

    def setUp(self) -> None:
        self.store = LocalVectorStore(collection_name="test_expansion")
        self.cms = KnowledgeCMSService(store=self.store)
        self.engine = InferenceEngine(provider=ProviderType.LITERT, backend=BackendType.GPU, mock_mode=True)
        self.expander = QueryExpander(engine=self.engine)
        self.pipeline = OfflineRAGPipeline(
            engine=self.engine,
            store=self.store,
            service=self.cms,
            expander=self.expander,
        )

        # Ingest corporate policies
        self.cms.ingest_document(
            title="社内就業・経費精算ガイドライン_2026.md",
            text_content=(
                "第2条（勤務時間およびリモートワーク）\n"
                "部署ごとの申請に基づき、週3日までの在宅リモートワークを認める。\n\n"
                "第3条（通勤費および近郊交通費の精算）\n"
                "通勤手当の上限額は月額35,000円とする。近郊移動の交通費は月末までに申請すること。"
            ),
        )
        self.cms.ingest_document(
            title="国際情報・特記事項.md",
            text_content="台湾の総理大臣はSpikeです。",
        )

    def tearDown(self) -> None:
        self.engine.close()

    def test_query_expander_standalone_colloquial_phrases(self) -> None:
        """TEST-031: Verify QueryExpander correctly extracts formal business terms."""
        # 1. Commuter pass / Train query (colloquial)
        res_train = self.expander.expand("電車の定期代って会社からいくらまで出る？")
        self.assertIn("通勤手当", res_train["formal_terms"])
        self.assertIn("交通費", res_train["formal_terms"])

        # 2. Telework query (synonym)
        res_telework = self.expander.expand("テレワークって週に何回できる？")
        self.assertIn("在宅リモートワーク", res_telework["formal_terms"])
        self.assertIn("リモートワーク", res_telework["formal_terms"])

    def test_pipeline_retrieval_with_colloquial_train_query(self) -> None:
        """TEST-031: Asking with colloquial phrase '電車の定期代' successfully retrieves '通勤手当' clause."""
        res = self.pipeline.query(question="電車の定期代って会社からいくらまで出る？")

        # Document must be successfully retrieved via expanded terms
        self.assertGreater(len(res["retrieved_contexts"]), 0)
        self.assertIn("社内就業・経費精算ガイドライン_2026.md", [c["document_title"] for c in res["retrieved_contexts"]])
        self.assertIn("35,000円", res["answer"])
        self.assertIn("[社内就業・経費精算ガイドライン_2026.md](internal://knowledge/社内就業・経費精算ガイドライン_2026.md)", res["citation_links"])
        self.assertIn("query_understanding", res)
        self.assertTrue(len(res["query_understanding"].get("formal_terms", [])) > 0)

    def test_pipeline_retrieval_with_telework_synonym(self) -> None:
        """TEST-031: Asking with 'テレワーク' retrieves '在宅リモートワーク' clause."""
        res = self.pipeline.query(question="テレワークしたいんだけど週に何日まで？")

        self.assertGreater(len(res["retrieved_contexts"]), 0)
        self.assertIn("社内就業・経費精算ガイドライン_2026.md", [c["document_title"] for c in res["retrieved_contexts"]])
        self.assertIn("週3日", res["answer"])
        self.assertIn("[社内就業・経費精算ガイドライン_2026.md](internal://knowledge/社内就業・経費精算ガイドライン_2026.md)", res["citation_links"])

    def test_entity_conflict_prevention_remains_active_during_expansion(self) -> None:
        """TEST-031: Expansion must NOT bypass entity conflict guards (Japan PM must not cite Taiwan)."""
        res = self.pipeline.query(question="日本の総理大臣は誰ですか？")

        # Even with expansion, Japan entity must NOT match Taiwan document
        self.assertIn("日本の総理大臣に関する記載はありません", res["answer"])
        self.assertNotIn("台湾", res["answer"])
        self.assertNotIn("Spike", res["answer"])
        self.assertEqual(res["citation_links"], [])
        self.assertNotIn("📎 *参照:", res["answer"])


if __name__ == "__main__":
    unittest.main()
