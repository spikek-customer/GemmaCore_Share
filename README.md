# 社内AIナレッジポータル & エージェント基盤 (Mac)

Google AI Edgeの推論スタック「**LiteRT-LM**」と「**Gemini API (Google GenAI SDK)**」を統合した、エンタープライズ向けセキュア・ハイブリッドAIナレッジ検索基盤です。

Office全般 (Word/Excel/PowerPoint)・PDF・CSVの万能取込、Google Workspace (SSO & Google Drive) 連携、LLMによるクエリ意図解釈・同義語展開、ハルシネーション抑制RAG、3言語多言語化（日本語・英語・繁体字中国語）、ChatGPT形式のスレッド管理、多階層ロール権限管理（RBAC）、および **MCP (Model Context Protocol)** サーバーを標準搭載しています。

---

## 🌟 主な機能

- 👥 **社員ライフサイクル & 階層型委譲RBAC**: 一般社員 (Viewer)、部門長 (Editor)、最高管理者 (Admin) の権限管理、部門リーダーへの安全な委譲管理、ワンクリック利用停止・安全削除、セッション自律保護。
- 🌐 **全画面3言語多言語化（i18n）**: 日本語（`ja`）、英語（`en`）、繁体字中国語（`zh-TW`）のワンクリック切り替え、CSSレイアウト保護。
- ☁️ **Google Workspace 統合連携**: Google OIDC によるハイブリッドSSO（JWKS電子署名検証・社内ドメイン制限）、Google Drive Changes API による増分差分同期＆Docs/Sheets/Slides自動エクスポート。
- 🔍 **インテリジェントRAG & 意図解釈**: 口語・俗語の正規業務用語展開 (`QueryExpander`)、主語・属性不一致の抑制による高度なハルシネーション防護。
- 📄 **万能ドキュメント取込**: Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), PDF, CSV, TXT のドラッグ＆ドロップ取込と文境界ベクトル分割。
- 💬 **スレッド式チャット & マルチテナント分離**: ユーザーセッション単位の厳格な会話隔離と履歴一括消去。
- 🤖 **Gemini動的モデル探索**: Google GenAI APIからの公開中モデル動的取得・リアルタイム切替。
- 🔒 **ゼロトラストセキュリティ & 監査トレール**: ゼロステート認証ゲート、大企業NAT対応動的レート制限（スライディングウィンドウ）、操作・診断ログ記録（最大1年保持・自動パージ）、APIキー難読化 masking。
- 🔌 **MCP 相互運用**: Claude DesktopやCursor等の外部AIツールと連携可能な MCP サーバー機能。

---

## 🚀 クイックスタート

### 1. 環境構築

```bash
# 仮想環境の作成と有効化 (macOS / Python 3.12 推奨)
python3 -m venv litert-env
source litert-env/bin/activate

# 依存パッケージのインストール
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. 環境変数の設定 (任意)

```bash
cp .env.example .env
# 必要に応じて .env 内の GEMINI_API_KEY や設定項目を編集
```

### 3. Webポータルの起動

```bash
python scripts/start_web.py
```

ブラウザで下記URLにアクセスします：
👉 **http://127.0.0.1:8000/**

#### 評価用デモアカウント

| ロール | ユーザーID | パスワード | 権限概要 |
| :--- | :--- | :--- | :--- |
| **最高管理者** | `admin` | `admin123` | 全機能・設定・ユーザー管理・監査ログ照会・動的レート制限調整 |
| **部門長 (Editor)** | `editor_user` | `password123` | チャット対話・資料取込・ナレッジCMS編集・自部署ユーザー管理 |
| **一般社員 (Viewer)** | `viewer_user` | `password123` | チャット対話・検索閲覧のみ |

---

## 📁 プロジェクト構成

```text
.
├── src/
│   ├── auth/         # RBAC・認証・セッション・レート制限・監査ログ
│   ├── core/         # ハイブリッド推論 (LiteRT-LM / Gemini)・設定永続化
│   ├── rag/          # ドキュメント解析・文境界分割・ベクトル検索・意図解釈
│   ├── sync/         # Google Drive 増分同期基盤
│   ├── harness/      # Agent Harness & MCP Server
│   └── web/          # REST API & WebUI (SPA + 3言語i18n)
├── scripts/          # 起動・運用スクリプト (macOS)
├── tests/            # 単体・結合・セキュリティテスト (全85件 100% PASS)
├── docs/             # 要件定義・基本設計・技術設計書・検討書
├── .env.example      # 環境変数テンプレート
├── .gitignore        # 機密・ビルド・ログ排除設定
└── requirements.txt  # 依存パッケージ定義
```

---

## 📜 利用条件・免責事項

- **著作権**: 本リポジトリ内のソースコードおよび関連ドキュメントの著作権は作成者に帰属し、著作権の放棄はいたしません。
- **利用目的**: 本成果物は個人の研究・技術検証・学習目的のためにのみ公開されています。
- **商用・商標利用の禁止**: 商用目的での利用（再頒布・商用サービスへの組み込み等）および商標・ロゴ等の無断利用・流用を禁止します。
