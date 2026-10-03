"""Unit and Integration Tests for Hybrid Inference, MCP Server, and Web API Controller.

Covers TEST-011, TEST-012, and TEST-013.
"""

import json
import unittest
from src.core.engine import InferenceEngine, ProviderType
from src.harness.mcp_server import MCPServer
from src.web.app import KnowledgeWebApp


class TestHybridAndMCP(unittest.TestCase):

    def test_hybrid_engine_cloud_gemini_dispatch(self) -> None:
        """TEST-011: Verify hybrid provider switching to Cloud Gemini API."""
        engine = InferenceEngine(provider=ProviderType.GEMINI, gemini_model="gemini-2.0-flash")
        answer = engine.generate("社内規程の要約をしてください。")
        self.assertIn("Cloud Gemini API", answer)
        self.assertIn("gemini-2.0-flash", answer)

    def test_mcp_server_protocol_tools_list_and_call(self) -> None:
        """TEST-012: Verify MCP tools/list and tools/call JSON-RPC 2.0 handling."""
        web_app = KnowledgeWebApp()
        mcp = MCPServer(cms_service=web_app.cms)

        # 1. tools/list request
        list_req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        list_res = mcp.handle_request(list_req)
        self.assertEqual(list_res["jsonrpc"], "2.0")
        self.assertEqual(list_res["id"], 1)
        tools = list_res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("search_knowledge", tool_names)
        self.assertIn("get_knowledge_block", tool_names)

        # 2. tools/call request
        call_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "search_knowledge", "arguments": {"query": "交通費", "limit": 2}},
        }
        call_res = mcp.handle_request(call_req)
        self.assertEqual(call_res["id"], 2)
        self.assertFalse(call_res["result"]["isError"])
        payload = json.loads(call_res["result"]["content"][0]["text"])
        self.assertIn("citations", payload)

    def test_web_app_controller_endpoints(self) -> None:
        """TEST-013: Verify KnowledgeWebApp controller handles chat, block CRUD, and search."""
        app = KnowledgeWebApp(store_path=":memory:", settings_path=":memory:")

        # Chat
        chat_res = app.chat("在宅リモートワークの条件")
        self.assertIn("answer", chat_res)
        self.assertIn("retrieved_contexts", chat_res)

        # Search simulator
        sim_res = app.search_simulator("AIツールの業務利用")
        self.assertGreater(sim_res["hit_count"], 0)

        # Settings
        setting_res = app.set_provider(provider="gemini", gemini_api_key="dummy_key")
        self.assertEqual(setting_res["active_provider"], "gemini")
        self.assertTrue(setting_res["has_gemini_key"])


if __name__ == "__main__":
    unittest.main()
