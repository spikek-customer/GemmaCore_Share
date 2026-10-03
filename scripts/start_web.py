#!/usr/bin/env python3
"""Start Standalone Knowledge Portal WebUI and Secure Enterprise REST API.

Runs on http://127.0.0.1:8000/ with zero mandatory external web server dependencies.
Provides REST endpoints with Strict Authentication Guard & Multi-Tier RBAC:
- Strict Auth Gate & Password Login (/api/v1/auth/login, /api/v1/auth/logout, /api/v1/auth/current)
- Multi-Thread Chat History (/api/v1/chat/threads/*)
- User & Role Grant Management (/api/v1/users/*)
- Audit Trail & Diagnostics (/api/v1/audit/logs, /api/v1/diagnostics/logs)
- Retention Policy (/api/v1/settings/retention)
- Universal Document Ingestion (/api/v1/upload/file, /api/v1/upload)
- Knowledge Block CMS CRUD (/api/v1/blocks/*)
- Search Simulator (/api/v1/search)
- Settings (/api/v1/settings)
- Model Context Protocol (/mcp)
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.auth.rate_limiter import RateLimiter
from src.auth.rbac import UserSession, sanitize_text
from src.web.app import KnowledgeWebApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PortalServer")

# Security Constraints & Rate Limiters
MAX_PAYLOAD_SIZE = 25 * 1024 * 1024  # 25MB max request entity size
login_rate_limiter = RateLimiter(max_requests=10, window_seconds=60.0)  # Max 10 login attempts / min per IP
chat_rate_limiter = RateLimiter(max_requests=30, window_seconds=60.0)   # Max 30 chat queries / min per IP/User


class PortalRequestHandler(SimpleHTTPRequestHandler):
    """Handles static files and secure enterprise REST API requests with Strict Authentication Gate."""

    app_instance: KnowledgeWebApp

    def __init__(self, *args, **kwargs):
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "web", "static"))
        super().__init__(*args, directory=static_dir, **kwargs)

    def end_headers(self) -> None:
        """Inject strict enterprise security headers on all responses (static and API)."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';",
        )
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK, extra_headers: Optional[Dict[str, str]] = None) -> None:
        """Helper to send JSON response with security headers."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _get_token(self) -> str:
        """Extract Bearer token from Authorization header."""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return ""

    def _require_auth(self, token: str) -> Optional[UserSession]:
        """Verify token; if invalid or missing, respond 401 Unauthorized and return None."""
        if not token:
            self._send_json(
                {"error": "UNAUTHORIZED", "message": "認証が必要です。ログインしてください。"},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return None
        session = self.app_instance.rbac.get_session(token)
        if not session:
            self._send_json(
                {"error": "UNAUTHORIZED", "message": "セッションが期限切れまたは無効です。再ログインしてください。"},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return None
        return session

    def _get_client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        token = self._get_token()
        query_params = parse_qs(parsed.query)

        try:
            # Public static assets
            if parsed.path in ["/", "/index.html", "/style.css", "/app.js", "/i18n.js", "/i18n_phrases.js", "/i18n_phrases_backend.js", "/favicon.ico"]:
                if parsed.path == "/":
                    self.path = "/index.html"
                super().do_GET()
                return

            # Public Auth check endpoint (returns user info or authenticated: false)
            if parsed.path == "/api/v1/auth/current":
                current_user = self.app_instance.get_current_user(token)
                self._send_json(current_user or {"authenticated": False})
                return

            # --- Protected API Endpoints (Require Valid Session Token) ---
            session = self._require_auth(token)
            if not session:
                return

            # 1. Users List & Stats
            if parsed.path == "/api/v1/users/stats":
                stats = self.app_instance.get_user_stats(token=token)
                self._send_json(stats)
                return

            elif parsed.path == "/api/v1/users":
                q_filter = query_params.get("q", [None])[0]
                role_filter = query_params.get("role", [None])[0]
                status_filter = query_params.get("status", [None])[0]
                users = self.app_instance.list_users(token=token, query=q_filter, role=role_filter, status=status_filter)
                self._send_json(users)
                return

            # 2. Chat Threads
            elif parsed.path == "/api/v1/chat/threads":
                threads = self.app_instance.list_chat_threads(token=token)
                self._send_json(threads)
                return

            elif parsed.path.startswith("/api/v1/chat/threads/"):
                thread_id = parsed.path.split("/")[-1]
                thread = self.app_instance.get_chat_thread(thread_id=thread_id, token=token)
                if not thread:
                    self.send_error(HTTPStatus.NOT_FOUND, "Thread not found")
                    return
                self._send_json(thread)
                return

            # 3. Audit & Diagnostics (Admin/Audit)
            elif parsed.path == "/api/v1/audit/logs":
                username_f = query_params.get("username", [None])[0]
                action_f = query_params.get("action", [None])[0]
                limit_f = int(query_params.get("limit", [100])[0])
                logs = self.app_instance.query_audit_logs(token=token, username=username_f, action=action_f, limit=limit_f)
                self._send_json(logs)
                return

            elif parsed.path == "/api/v1/diagnostics/logs":
                limit_f = int(query_params.get("limit", [100])[0])
                logs = self.app_instance.query_diagnostics_logs(token=token, limit=limit_f)
                self._send_json(logs)
                return

            # 4. Settings
            elif parsed.path == "/api/v1/settings":
                settings = self.app_instance.get_settings(token=token)
                self._send_json(settings)
                return

            elif parsed.path == "/api/v1/models":
                models = self.app_instance.get_available_models()
                self._send_json({"models": models})
                return

            # 5. Knowledge Blocks
            elif parsed.path == "/api/v1/blocks":
                q = query_params.get("q", [None])[0]
                blocks = self.app_instance.list_blocks(query=q, token=token)
                self._send_json(blocks)
                return

            # 6. Google Drive Synchronization (Viewer+ for status, Admin for folders)
            elif parsed.path == "/api/v1/drive/status":
                status = self.app_instance.handle_get_drive_status(token=token)
                self._send_json(status)
                return

            elif parsed.path == "/api/v1/drive/folders":
                folders = self.app_instance.handle_get_drive_folders(token=token)
                self._send_json({"folders": folders})
                return

            # Fallback static
            super().do_GET()

        except PermissionError as pe:
            self._send_json({"error": "FORBIDDEN", "message": str(pe)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            logger.error(sanitize_text(f"GET error on {parsed.path}: {e}"))
            self._send_json({"error": "SERVER_ERROR", "message": sanitize_text(str(e))}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        token = self._get_token()
        ip_addr = self._get_client_ip()
        body = self._read_json_body()
        if body is None:
            return

        try:
            # 1. Public Authentication (Login & Google SSO)
            if parsed.path == "/api/v1/auth/login":
                settings_cfg = self.app_instance.settings_manager.load_settings()
                limit_login = settings_cfg.get("rate_limit_login", 20)
                if limit_login > 0:
                    login_rate_limiter.max_requests = limit_login
                    allowed, retry_after = login_rate_limiter.is_allowed(ip_addr)
                    if not allowed:
                        self._send_json(
                            {
                                "error": "TOO_MANY_REQUESTS",
                                "message": f"ログイン試行回数の上限（毎分{limit_login}回）に達しました。{int(retry_after)}秒後に再試行してください。",
                            },
                            status=HTTPStatus.TOO_MANY_REQUESTS,
                            extra_headers={"Retry-After": str(int(retry_after))},
                        )
                        return
                username = body.get("username", "")
                password = body.get("password", "")
                res = self.app_instance.login(username=username, password=password, ip_address=ip_addr)
                self._send_json(res)
                return

            elif parsed.path == "/api/v1/auth/google":
                id_token = body.get("id_token", "")
                res = self.app_instance.handle_google_login(id_token=id_token, ip_address=ip_addr)
                self._send_json(res)
                return

            # Legacy/Dev Switcher (Blocked by default in production; only enabled when ALLOW_DEV_SWITCH=true)
            elif parsed.path == "/api/v1/auth/switch":
                if os.environ.get("ALLOW_DEV_SWITCH", "").lower() not in ("true", "1"):
                    self._send_json(
                        {"error": "FORBIDDEN", "message": "開発用スイッチ機能は本番環境では無効化されています。"},
                        status=HTTPStatus.FORBIDDEN,
                    )
                    return
                username = body.get("username", "viewer_user")
                res = self.app_instance.switch_user(username, ip_address=ip_addr)
                self._send_json(res)
                return

            # --- Protected POST APIs (Require Valid Session Token) ---
            session = self._require_auth(token)
            if not session:
                return

            # 2. Logout
            if parsed.path == "/api/v1/auth/logout":
                res = self.app_instance.logout(token=token, ip_address=ip_addr)
                self._send_json(res)
                return

            # 3. User Management (Admin)
            elif parsed.path == "/api/v1/users":
                username = body.get("username", "")
                display_name = body.get("display_name", "")
                role = body.get("role", "viewer")
                department = body.get("department", "一般")
                password = body.get("password", "password123")
                notes = body.get("notes", "")
                user = self.app_instance.create_user(
                    username=username,
                    display_name=display_name,
                    role=role,
                    department=department,
                    password=password,
                    notes=notes,
                    token=token,
                    ip_address=ip_addr,
                )
                self._send_json(user, status=HTTPStatus.CREATED)
                return

            elif parsed.path.startswith("/api/v1/users/") and parsed.path.endswith("/reset-password"):
                target_user = parsed.path.split("/")[4]
                new_password = body.get("password", "")
                res = self.app_instance.reset_user_password(
                    target_username=target_user,
                    new_password=new_password,
                    token=token,
                    ip_address=ip_addr,
                )
                self._send_json(res)
                return

            elif parsed.path.startswith("/api/v1/users/") and parsed.path.endswith("/unlock"):
                target_user = parsed.path.split("/")[4]
                res = self.app_instance.unlock_user(
                    target_username=target_user,
                    token=token,
                    ip_address=ip_addr,
                )
                self._send_json(res)
                return


            # 4. Chat & Threads
            elif parsed.path == "/api/v1/chat/threads":
                title = body.get("title", "新しいチャット")
                thread = self.app_instance.create_chat_thread(token=token, title=title)
                self._send_json(thread, status=HTTPStatus.CREATED)
                return

            elif parsed.path == "/api/v1/chat":
                settings_cfg = self.app_instance.settings_manager.load_settings()
                limit_chat = settings_cfg.get("rate_limit_chat", 60)
                client_key = session.username if session else (token or ip_addr)
                if limit_chat > 0:
                    chat_rate_limiter.max_requests = limit_chat
                    allowed, retry_after = chat_rate_limiter.is_allowed(client_key)
                    if not allowed:
                        self._send_json(
                            {
                                "error": "TOO_MANY_REQUESTS",
                                "message": f"チャット対話リクエストが上限（毎分{limit_chat}回）に達しました。{int(retry_after)}秒後に再試行してください。",
                            },
                            status=HTTPStatus.TOO_MANY_REQUESTS,
                            extra_headers={"Retry-After": str(int(retry_after))},
                        )
                        return
                question = body.get("question", "")
                thread_id = body.get("thread_id")
                res = self.app_instance.chat(question=question, thread_id=thread_id, token=token, ip_address=ip_addr)
                self._send_json(res)
                return

            # 5. Search Simulator
            elif parsed.path == "/api/v1/search":
                query = body.get("query", "")
                limit = int(body.get("limit", 5))
                res = self.app_instance.search_simulator(query=query, limit=limit, token=token)
                self._send_json(res)
                return

            # 6. Create Block
            elif parsed.path == "/api/v1/blocks":
                title = body.get("document_title", "社内資料")
                text = body.get("text", "")
                locator = body.get("locator", "")
                block = self.app_instance.create_block(title=title, text=text, locator=locator, token=token, ip_address=ip_addr)
                self._send_json(block, status=HTTPStatus.CREATED)
                return

            # 7. Universal File Upload (PDF, Word, Excel, PPTX, CSV, TXT via Base64)
            elif parsed.path == "/api/v1/upload/file":
                filename = body.get("filename", "untitled_file")
                data_b64 = body.get("data_base64", "")
                if not data_b64:
                    raise ValueError("ファイルデータが空です。")

                file_bytes = base64.b64decode(data_b64)
                res = self.app_instance.upload_document_file(
                    filename=filename,
                    file_bytes=file_bytes,
                    token=token,
                    ip_address=ip_addr,
                )
                self._send_json(res, status=HTTPStatus.CREATED)
                return

            # Legacy Text Upload
            elif parsed.path == "/api/v1/upload":
                title = body.get("title", "未命名文書")
                content = body.get("content", "")
                res = self.app_instance.upload_document(title=title, content=content, token=token, ip_address=ip_addr)
                self._send_json(res, status=HTTPStatus.CREATED)
                return

            # 8. Settings (Model / Retention / Rate Limits)
            elif parsed.path == "/api/v1/settings":
                provider = body.get("provider", "litert")
                gemini_key = body.get("gemini_api_key")
                gemini_model = body.get("gemini_model") or "gemini-3.5-flash-lite"
                rate_limit_login = body.get("rate_limit_login")
                rate_limit_chat = body.get("rate_limit_chat")
                res = self.app_instance.set_provider(
                    provider=provider,
                    gemini_api_key=gemini_key,
                    gemini_model=gemini_model,
                    rate_limit_login=rate_limit_login,
                    rate_limit_chat=rate_limit_chat,
                    token=token,
                    ip_address=ip_addr,
                )
                self._send_json(res)
                return

            elif parsed.path == "/api/v1/settings/retention":
                days = int(body.get("days", 365))
                saved_days = self.app_instance.set_retention_days(days=days, token=token, ip_address=ip_addr)
                self._send_json({"status": "SUCCESS", "retention_days": saved_days})
                return

            # 8.5 Model Discovery (Real-time Google GenAI Query)
            elif parsed.path == "/api/v1/models/discover":
                api_key = body.get("api_key")
                res = self.app_instance.discover_gemini_models(api_key=api_key, token=token)
                self._send_json(res)
                return

            # 8.6 Google Drive Synchronization (Editor+ for Sync, Admin for Folders)
            elif parsed.path == "/api/v1/drive/sync":
                simulated = body.get("simulated_changes")
                res = self.app_instance.handle_drive_sync(
                    token=token,
                    ip_address=ip_addr,
                    simulated_changes=simulated,
                )
                self._send_json(res)
                return

            elif parsed.path == "/api/v1/drive/folders":
                folders = body.get("folders", [])
                res = self.app_instance.handle_set_drive_folders(
                    token=token,
                    folders=folders,
                    ip_address=ip_addr,
                )
                self._send_json(res)
                return

            # 9. MCP JSON-RPC
            elif parsed.path == "/mcp":
                res = self.app_instance.handle_mcp(body)
                self._send_json(res)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        except PermissionError as pe:
            self._send_json({"error": "FORBIDDEN", "message": str(pe)}, status=HTTPStatus.FORBIDDEN)
        except ValueError as ve:
            self._send_json({"error": "BAD_REQUEST", "message": str(ve)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as e:
            logger.error(sanitize_text(f"POST error on {parsed.path}: {e}"))
            self._send_json({"error": "SERVER_ERROR", "message": sanitize_text(str(e))}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        token = self._get_token()
        ip_addr = self._get_client_ip()
        body = self._read_json_body()
        if body is None:
            return

        session = self._require_auth(token)
        if not session:
            return

        try:
            # Update user status (Active / Suspended)
            if parsed.path.startswith("/api/v1/users/") and parsed.path.endswith("/status"):
                target_user = parsed.path.split("/")[4]
                is_active = bool(body.get("is_active", True))
                res = self.app_instance.toggle_user_status(target_username=target_user, is_active=is_active, token=token, ip_address=ip_addr)
                self._send_json(res)
                return

            # Update user role
            elif parsed.path.startswith("/api/v1/users/") and parsed.path.endswith("/role"):
                target_user = parsed.path.split("/")[4]
                new_role = body.get("role", "viewer")
                res = self.app_instance.update_user_role(target_username=target_user, new_role=new_role, token=token, ip_address=ip_addr)
                self._send_json(res)
                return

            # Update full user details
            elif parsed.path.startswith("/api/v1/users/"):
                target_user = parsed.path.split("/")[4]
                res = self.app_instance.update_user(
                    target_username=target_user,
                    display_name=body.get("display_name"),
                    role=body.get("role"),
                    department=body.get("department"),
                    notes=body.get("notes"),
                    token=token,
                    ip_address=ip_addr,
                )
                self._send_json(res)
                return

            # Update knowledge block
            elif parsed.path.startswith("/api/v1/blocks/"):
                block_id = parsed.path.split("/")[-1]
                new_text = body.get("text", "")
                updated = self.app_instance.update_block(block_id=block_id, text=new_text, token=token, ip_address=ip_addr)
                self._send_json(updated)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        except PermissionError as pe:
            self._send_json({"error": "FORBIDDEN", "message": str(pe)}, status=HTTPStatus.FORBIDDEN)
        except KeyError as ke:
            self.send_error(HTTPStatus.NOT_FOUND, str(ke))
        except Exception as e:
            logger.error(sanitize_text(f"PUT error on {parsed.path}: {e}"))
            self._send_json({"error": "SERVER_ERROR", "message": sanitize_text(str(e))}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        token = self._get_token()
        ip_addr = self._get_client_ip()

        session = self._require_auth(token)
        if not session:
            return

        try:
            # Clear all chat threads
            if parsed.path == "/api/v1/chat/threads":
                query_params = parse_qs(parsed.query)
                all_users = query_params.get("all", ["false"])[0].lower() == "true"
                res = self.app_instance.clear_chat_threads(token=token, all_users=all_users, ip_address=ip_addr)
                self._send_json(res)
                return

            # Delete single chat thread
            elif parsed.path.startswith("/api/v1/chat/threads/"):
                thread_id = parsed.path.split("/")[-1]
                res = self.app_instance.delete_chat_thread(thread_id=thread_id, token=token)
                self._send_json(res)
                return

            # Delete knowledge block
            elif parsed.path.startswith("/api/v1/blocks/"):
                block_id = parsed.path.split("/")[-1]
                res = self.app_instance.delete_block(block_id=block_id, token=token, ip_address=ip_addr)
                self._send_json(res)
                return

            # Delete user
            elif parsed.path.startswith("/api/v1/users/"):
                target_user = parsed.path.split("/")[-1]
                res = self.app_instance.delete_user(target_username=target_user, token=token, ip_address=ip_addr)
                self._send_json(res)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        except PermissionError as pe:
            self._send_json({"error": "FORBIDDEN", "message": str(pe)}, status=HTTPStatus.FORBIDDEN)
        except ValueError as ve:
            self._send_json({"error": "BAD_REQUEST", "message": str(ve)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as e:
            logger.error(sanitize_text(f"DELETE error on {parsed.path}: {e}"))
            self._send_json({"error": "SERVER_ERROR", "message": sanitize_text(str(e))}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        if content_length > MAX_PAYLOAD_SIZE:
            self._send_json(
                {
                    "error": "PAYLOAD_TOO_LARGE",
                    "message": f"リクエストサイズ（{content_length} bytes）が上限（{MAX_PAYLOAD_SIZE} bytes）を超過しています。",
                },
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return None
        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Enterprise Knowledge Portal WebUI")
    parser.add_argument("--port", type=int, default=8000, help="HTTP Server Port (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Binding host (default: 127.0.0.1)")
    args = parser.parse_args()

    # Initialize Backend Application Controller
    logger.info("Initializing Enterprise Knowledge Application...")
    app = KnowledgeWebApp()
    PortalRequestHandler.app_instance = app

    server_address = (args.host, args.port)
    httpd = ThreadingHTTPServer(server_address, PortalRequestHandler)
    print("=" * 72)
    print(f"🚀 社内AIナレッジポータル (v3.2 Enterprise) が起動しました")
    print(f"🔗 URL: http://{args.host}:{args.port}/")
    print("🔒 セキュリティ: 厳格認証ゲートウェイ (Strict Auth Gate & 401 Guard) 有効")
    print("📁 取込対応: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), TXT/CSV")
    print("💎 AIモデル: Gemini 3.5 Flash Lite ＆ LiteRT-LM (Apple Silicon Metal)")
    print("=" * 72)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 ポータルサーバーを安全にシャットダウンしています...")
        httpd.shutdown()
        logger.info("Server gracefully stopped.")


if __name__ == "__main__":
    main()
