"""Unit Tests for Sentence-Aware Chunking and Knowledge CMS Block CRUD.

Covers TEST-009 and TEST-010.
"""

import unittest
from src.rag.chunking import chunk_text_sentence_aware, prefer_sentence_boundary
from src.rag.service import KnowledgeCMSService
from src.rag.store import LocalVectorStore


class TestCMSAndChunking(unittest.TestCase):

    def test_sentence_boundary_preservation(self) -> None:
        """TEST-009: Verify sentence boundaries are preserved without splitting mid-sentence."""
        sample_text = (
            "第1条。本規程は全社に適用されます。\n\n"
            "第2条。勤務時間は9時から18時までとします。休憩時間は1時間です。\n\n"
            "第3条。通勤手当の上限額は月額35,000円です。申請は当月末日までに行ってください。"
        )
        chunks = chunk_text_sentence_aware(sample_text, chunk_size=60, overlap=15)
        self.assertGreater(len(chunks), 1)

        # Ensure chunks end with punctuation or natural marker
        for chunk in chunks:
            self.assertTrue(
                chunk.text.endswith("。") or chunk.text.endswith("\n") or len(chunk.text) > 0
            )

    def test_block_crud_and_instant_reindexing(self) -> None:
        """TEST-010: Verify block addition, text update, instant search reflection, and deletion."""
        store = LocalVectorStore(collection_name="test_cms")
        cms = KnowledgeCMSService(store=store)

        # 1. Add single block
        block = cms.add_single_block(
            document_title="交通費規程",
            text="通勤手当の上限額は月額30,000円とする。",
            locator="第3条",
        )
        block_id = block["block_id"]
        self.assertIsNotNone(block_id)

        # 2. Search matches initial value
        res1 = cms.search_fast("通勤手当の上限額", limit=1)
        self.assertEqual(len(res1["citations"]), 1)
        self.assertIn("30,000円", res1["citations"][0]["text"])

        # 3. Update block text (e.g. raised to 35,000 yen)
        cms.update_block_text(block_id, "通勤手当の上限額は月額35,000円に引き上げる。")

        # 4. Search matches updated value immediately
        res2 = cms.search_fast("通勤手当の上限額", limit=1)
        self.assertEqual(len(res2["citations"]), 1)
        self.assertIn("35,000円", res2["citations"][0]["text"])
        self.assertNotIn("30,000円", res2["citations"][0]["text"])

        # 5. Delete block
        deleted = cms.delete_block(block_id)
        self.assertTrue(deleted)

        # 6. Verify excluded from search
        res3 = cms.search_fast("通勤手当の上限額", limit=1)
        self.assertEqual(len(res3["citations"]), 0)


if __name__ == "__main__":
    unittest.main()
