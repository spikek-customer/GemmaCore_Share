# システム改訂・アップグレード記録 (UPGRADE NOTES)

* **プロジェクト名**：GemmaCore_Mac (LiteRT-LM & Gemini ハイブリッド・ナレッジ管理・エージェント基盤)
* **最新バージョン**：**v4.4 Enterprise Multi-Cloud & Security Hardened Edition**
* **最新改訂日**：2026-10-04

---

## 1. バージョン別改訂サマリー

### v4.4 Enterprise Multi-Cloud & Security Hardened Edition (2026-10-04)
* **最新仕様同期・セキュリティ堅牢化・依存定義完全化**:
  * **macOS Apple Silicon Metal環境の保護**: メインの Apple Silicon Metal 推論、POSIX パーミッション、`scripts/setup_env.sh`, `scripts/start_web.py` の実行権限を 100% 維持。
  * **依存定義完全化 (`requirements.txt`)**: Office・PDFパーサー（`pypdf`, `python-docx`, `openpyxl`, `python-pptx`）および `google-auth` を明示追加。
  * **自動テスト**: 全85件の自動テストが 100% PASS。

### v4.3.1 Enterprise NAT & Dynamic Rate Limiting (2026-10-03)
* **大企業NAT/プロキシ対応 & 動的レート制限管理**:
  * **ログインAPI 60秒スライディングウィンドウ制限**: 試行回数を秒単位で追跡し、超過時は `Retry-After: <秒数>` を返却。
  * **チャットAPIのアカウント単位分離 (`session.username`)**: 10,000人規模の大企業で単一NAT/プロキシIPを共有している環境でも、社員ごとに独立した制限バケット（デフォルト60回/分）を割り当て、巻き添え遮断を完全防止。
  * **リバースプロキシクライアントIP抽出**: `_get_client_ip()` により `X-Forwarded-For` ヘッダーから真のクライアントIPを抽出。
  * **管理画面からの動的設定**: `system_settings.json` / `/api/v1/settings`（GET/POST）により `rate_limit_login` および `rate_limit_chat`（`0` 設定で無制限化）をサーバー再起動不要で即時変更可能。

### v4.3 Enterprise Security Hardening & Zero-Trust Defense (2026-10-03)
* **包括的セキュリティ脆弱性監査・改修**:
  * **開発用バックドア排除**: `POST /api/v1/auth/switch` を本番環境でデフォルト無効化（403 Forbidden）。
  * **Google OIDC 電子署名検証**: `google.oauth2.id_token.verify_oauth2_token` によるGoogle公開鍵（JWKS）暗号署名検証を必須化。
  * **Stored DOM XSS 根絶**: 管理画面のインライン `onclick` 文字列結合を全廃し、`data-username` 属性とイベントデリゲーションへ完全移行。
  * **タイミング攻撃防御**: 存在しないユーザー名での認証試行時にもダミーPBKDF2計算（100,000反復）を実行し、応答時間差によるユーザー列挙を防止。
  * **リクエストサイズ制限**: `MAX_PAYLOAD_SIZE = 25MB` 上限を設定し、413 Payload Too Large でOOM DoSを防止。
  * **センシティブ情報マスキング**: 一般社員（Viewer）への返却データから人事メモやロック状態を完全マスキング。
  * **設定ファイル権限保護**: `system_settings.json` のパーミッションを `0600` に強制設定。
  * **セキュリティヘッダー**: レスポンスに `Content-Security-Policy` および `Permissions-Policy` を送出。

### v4.2 Enterprise i18n & Multi-language Readability Edition (2026-10-03)
* **全画面3言語多言語化（日本語・英語・繁体字中国語）& 国際化レイアウト保護**:
  * `src/web/static/i18n.js`（3言語辞書エンジン）＋ `i18n_phrases.js`（DOM走査・MutationObserver・正規表現パターン）。
  * ワンクリック言語切替（🌐 ドロップダウン）、`localStorage`（`gcomm_lang`）永続化。
  * 英語の単語長拡大に対応する `word-break: break-word`、繁体字中国語専用フォント（`PingFang TC`, `Microsoft JhengHei`）および `line-height: 1.7` 設定。

### v4.1 Enterprise Security & Full Scroll Edition (2026-10-03)
* **ブルートフォース総攻撃防護（アカウントロックアウト）& 無操作セッションタイムアウト**:
  * 連続5回パスワード失敗で自動5分間一時ロック（`locked_until = now + 300`）。期間中の試行は照合せず即座に403遮断。管理者・部門管理者による即時アンロック。
  * 最終操作から30分無操作でセッション失効（`session.touch()` によるアイドルタイマー更新）。
  * 全モーダル共通の二重スクロール保護（`max-height: calc(100vh - 48px); overflow-y: auto; margin: auto;`）。

### v4.0 Delegated RBAC Edition (2026-10-03)
* **大企業向け階層型委譲アクセス制御（2層ユーザー管理）**:
  * 編集長（Editor / 部門管理者）に自部署の閲覧者（Viewer）・編集長（Editor）のライフサイクル管理を委譲。
  * 管理者（Admin）アカウントの不可侵保護（上位保護）および管理者ロール付与の禁止（権限昇格防止）。

### v3.8 Google Workspace Integration Edition (2026-10-03)
* **Google Workspace OIDC SSO & Google Drive Changes API 常時増分同期**:
  * 社内ドメイン制限（`hd`）、JITプロビジョニング、Docs/Sheets/Slides 自動エクスポート、削除即時パージ、ETag重複スキップ、フォルダ別ロール権限ACL統制、リアルタイム同期ダッシュボード。

### v3.7〜v1.0
* 社員ライフサイクル管理（入社・異動・退社・安全削除ガード・SQLite永続化）、LLMクエリ理解・意図解釈・同義語展開、RAG排他エンティティ制御、ChatGPT形式会話履歴管理、Office/PDF万能パース、ゼロステート認証ゲート、多階層RBAC、ハイブリッド推論（LiteRT-LM & Gemini SDK）。

---

## 2. データベースマイグレーションと互換性

| データベースファイル | 対象バージョン | 内容・テーブル構造 | 互換性 |
| :--- | :---: | :--- | :---: |
| `scratch/users_rbac.db` | v3.7〜v4.4 | `users (username, display_name, role, department, password_hash, is_active, failed_attempts, locked_until, notes, created_at, updated_at)` | 自動マイグレーション対応・完全永続化 |
| `scratch/system_audit.db` | v3.1〜v4.4 | `audit_logs`, `diagnostics_logs` | 完全後方互換 |
| `scratch/chat_history.db` | v3.1〜v4.4 | `threads (thread_id, title, user_id, created_at, updated_at)`, `messages` | 完全後方互換（マルチテナント分離） |
| `scratch/drive_sync.db` | v3.8〜v4.4 | `drive_sync_state`, `synced_files`, `folder_configs` | 新設・完全永続化 |
| `scratch/system_settings.json` | v3.3〜v4.4 | JSON（Mode: 0600, `active_provider`, `gemini_model`, `gemini_api_key`, `retention_days`, `rate_limit_login`, `rate_limit_chat`） | 完全後方互換・動的設定対応 |
| `data/qdrant_storage/` | v1.0〜v4.4 | `company_knowledge` ベクトルコレクション | 完全互換（マルチフォーマット対応） |

---

## 3. テスト自動化・回帰検証結果

* **テストフレームワーク**: pytest 9.1.1
* **自動テスト件数**: **全85テスト**
* **テスト結果**: **85 passed, 0 failed (100% PASS)**
* **検証対象内訳**:
  * コア推論・CLI・耐障害性 (4件)
  * 文境界チャンキング・CMS (2件)
  * オフラインRAG・ベクトル検索 (3件)
  * マルチモーダル (2件)
  * エージェント契約 (3件)
  * クラウドハイブリッド推論・MCP・REST API (3件)
  * 多階層RBAC・セキュリティ・機密マスク・Git境界 (7件)
  * エンタープライズ履歴・ユーザー・監査・診断・パージ (5件)
  * ゼロステート認証・万能マルチフォーマット取込 (7件)
  * ユーザー分離・設定永続化・全履歴削除・モデル探索 (5件)
  * RAG排他制御・引用抑制・ハルシネーション防護 (4件)
  * LLMクエリ理解・意図解釈・同義語展開・揺らぎ吸収 (4件)
  * 社員ライフサイクル管理・SQLite永続化・安全削除ガード (6件)
  * Google Workspace SSO・Drive常時差分同期・ACL統制 (6件)
  * 階層型委譲RBAC・管理者保護・権限昇格禁止 (4件)
  * アカウントロックアウト・セッションアイドルタイムアウト (4件)
  * 全画面多言語化（i18n: ja/en/zh-TW）・レイアウト安全 (9件)
  * セキュリティ脆弱性対策・Google暗号署名・XSS・レート制限 (7件)

---

## 4. 利用条件・免責事項

* **著作権**: 本リポジトリ内のソースコードおよび関連ドキュメントの著作権は作成者に帰属し、著作権の放棄はいたしません。
* **利用目的**: 本成果物は個人の研究・技術検証・学習目的のためにのみ公開されています。
* **商用・商標利用の禁止**: 商用目的での利用（再頒布・商用サービスへの組み込み等）および商標・ロゴ等の無断利用・流用を禁止します。
