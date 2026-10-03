"""Model Context Protocol (MCP) Server for Knowledge Retrieval.

Implements JSON-RPC 2.0 handlers compliant with Anthropic/Cursor/OpenClaw MCP specifications.
Exposes internal company knowledge base as standard callable tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.rag.service import KnowledgeCMSService

logger = logging.getLogger(__name__)


class MCPServer:
    """Handles Model Context Protocol JSON-RPC requests."""

    def __init__(self, cms_service: Optional[KnowledgeCMSService] = None) -> None:
        self.cms = cms_service or KnowledgeCMSService()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return MCP-compliant tool specifications."""
        return [
            {
                "name": "search_knowledge",
                "description": "社内ナレッジ規程・文書を検索し、関連チャンクと出典を返却します。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "検索キーワードまたは質問文",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "取得する最大件数 (デフォルト: 5)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_knowledge_block",
                "description": "特定のナレッジブロックの詳細本文を取得します。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "block_id": {
                            "type": "string",
                            "description": "ナレッジブロックの一意識別子",
                        }
                    },
                    "required": ["block_id"],
                },
            },
        ]

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch JSON-RPC 2.0 request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.get_tool_definitions()},
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})

            if tool_name == "search_knowledge":
                query = args.get("query", "")
                limit = int(args.get("limit", 5))
                res = self.cms.search_fast(query=query, limit=limit)
                content_text = json.dumps(res, ensure_ascii=False, indent=2)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": content_text}],
                        "isError": False,
                    },
                }

            elif tool_name == "get_knowledge_block":
                block_id = args.get("block_id", "")
                block = self.cms.store.get_block(block_id)
                if not block:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Error: Block '{block_id}' not found"}],
                            "isError": True,
                        },
                    }
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(block, ensure_ascii=False, indent=2)}],
                        "isError": False,
                    },
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {tool_name}"},
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": f"Invalid Request: unknown method '{method}'"},
        }
