"""Test Chat Grounding & Retrieval Precision (Fix for Japan vs Taiwan prime minister issue).

TEST-025: Verify RAG assistant correctly distinguishes subjects (Japan vs Taiwan)
and avoids false attribution / hallucination, and confirms unrelated guidelines
are not cited.
"""

from __future__ import annotations

import unittest
from src.core.engine import BackendType, InferenceEngine, ProviderType
from src.rag.pipeline import OfflineRAGPipeline
from src.rag.service import KnowledgeCMSService
from src.rag.store import LocalVectorStore
from src.web.app import KnowledgeWebApp


class TestChatGroundingFix(unittest.TestCase):
    """Verifies that RAG chat does not attribute Taiwan info when queried about Japan."""

    def setUp(self) -> None:
        self.store = LocalVectorStore(collection_name="test_grounding")
        self.cms = KnowledgeCMSService(store=self.store)
        self.engine = InferenceEngine(provider=ProviderType.LITERT, backend=BackendType.GPU, mock_mode=True)
        self.pipeline = OfflineRAGPipeline(engine=self.engine, store=self.store, service=self.cms)

        # Ingest corporate documents
        self.cms.ingest_document(
            title="国際情報・特記事項.md",
            text_content="台湾の総理大臣はSpikeです。国際情勢特記事項として記録されています。",
        )
        self.cms.ingest_document(
            title="社内就業・経費精算ガイドライン_2026.md",
            text_content="第1条 通勤手当の上限額は月額35,000円です。近郊交通費は月末までに申請してください。",
        )

    def tearDown(self) -> None:
        self.engine.close()

    def test_japan_query_does_not_hallucinate_taiwan_info(self) -> None:
        """TEST-025: Asking about Japan Prime Minister must NOT claim Taiwan PM, provide unsolicited notes, or cite documents."""
        res = self.pipeline.query(question="日本の総理大臣は誰ですか？")

        # Answer must acknowledge that Japan's PM is NOT in the company knowledge
        self.assertIn("日本の総理大臣に関する記載はありません", res["answer"])
        # Must NOT mention Taiwan or Chen Spike in any form
        self.assertNotIn("台湾", res["answer"])
        self.assertNotIn("Spike", res["answer"])
        # Citation links must be strictly suppressed
        self.assertEqual(res["citation_links"], [])
        self.assertNotIn("📎 *参照:", res["answer"])

    def test_taiwan_president_query_does_not_hallucinate_pm_info(self) -> None:
        """TEST-025: Asking about Taiwan President must NOT cite or bring up Prime Minister Chen Spike."""
        res = self.pipeline.query(question="台湾の大統領は誰ですか？")

        # Answer must acknowledge that Taiwan's President is NOT in the company knowledge
        self.assertIn("台湾の大統領に関する記載はありません", res["answer"])
        # Must NOT mention Prime Minister or Chen Spike
        self.assertNotIn("総理大臣", res["answer"])
        self.assertNotIn("Spike", res["answer"])
        # Citation links must be strictly suppressed
        self.assertEqual(res["citation_links"], [])
        self.assertNotIn("📎 *参照:", res["answer"])

    def test_taiwan_pm_query_returns_taiwan_pm(self) -> None:
        """TEST-025: Asking about Taiwan Prime Minister correctly answers with Chen Spike and citations."""
        res = self.pipeline.query(question="台湾の総理大臣は誰ですか？")

        self.assertIn("Spike", res["answer"])
        self.assertIn("国際情報・特記事項.md", [c["document_title"] for c in res["retrieved_contexts"]])
        self.assertIn("[国際情報・特記事項.md](internal://knowledge/国際情報・特記事項.md)", res["citation_links"])
        self.assertIn("📎 *参照: [国際情報・特記事項.md](internal://knowledge/国際情報・特記事項.md)*", res["answer"])

    def test_app_chat_endpoint_grounding_and_suppression(self) -> None:
        """TEST-025: Verify full KnowledgeWebApp chat integration with strict grounding."""
        from src.core.engine import ProviderType
        app = KnowledgeWebApp(store_path=":memory:", default_provider=ProviderType.LITERT, settings_path=":memory:")
        admin_session = app.switch_user("admin_user")
        token = admin_session["session_id"]

        # Add the dummy knowledge
        app.create_block(
            title="国際情報・特記事項.md",
            locator="国際情報・特記事項.md",
            text="台湾の総理大臣はSpikeです。",
            token=token,
        )

        # 1. Query about Japan Prime Minister
        chat_japan = app.chat(question="日本の総理大臣は誰ですか？", token=token)
        self.assertIn("日本の総理大臣に関する記載はありません", chat_japan["answer"])
        self.assertNotIn("台湾", chat_japan["answer"])
        self.assertNotIn("Spike", chat_japan["answer"])
        self.assertEqual(chat_japan.get("citation_links", []), [])
        self.assertNotIn("📎 *参照:", chat_japan["answer"])

        # 2. Query about Taiwan President
        chat_pres = app.chat(question="台湾の大統領は誰ですか？", token=token)
        self.assertIn("台湾の大統領に関する記載はありません", chat_pres["answer"])
        self.assertNotIn("総理大臣", chat_pres["answer"])
        self.assertNotIn("Spike", chat_pres["answer"])
        self.assertEqual(chat_pres.get("citation_links", []), [])
        self.assertNotIn("📎 *参照:", chat_pres["answer"])

        # 3. Query about Taiwan Prime Minister
        chat_taiwan = app.chat(question="台湾の総理大臣は誰ですか？", token=token)
        self.assertIn("Spike", chat_taiwan["answer"])
        self.assertIn("[国際情報・特記事項.md](internal://knowledge/国際情報・特記事項.md)", chat_taiwan.get("citation_links", []))
        self.assertIn("📎 *参照: [国際情報・特記事項.md](internal://knowledge/国際情報・特記事項.md)*", chat_taiwan["answer"])


if __name__ == "__main__":
    unittest.main()
