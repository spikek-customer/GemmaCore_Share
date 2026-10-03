/**
 * i18n.js - Enterprise Internationalization & Localization Engine
 * Supports: Japanese (ja), English (en), Traditional Chinese (zh-TW)
 */

(function () {
  const STORAGE_KEY = 'gcomm_lang';

  const translations = {
    ja: {
      // Header & Navigation
      app_title: "社内AIナレッジポータル",
      app_subtitle: "LiteRT-LM & Google Gemini ハイブリッド知識基盤 (v4.2 Enterprise)",
      logged_in_as: "👤 ログイン中:",
      btn_logout: "🚪 ログアウト",
      role_admin: "👑 管理者",
      role_editor: "✏️ 編集長",
      role_viewer: "👤 閲覧者",
      mode_local: "ローカル推論 (LiteRT-LM)",
      mode_cloud: "クラウド推論 (Google Gemini)",
      
      tab_chat: "社内チャット",
      tab_upload: "資料ファイル一括登録",
      tab_cms: "ナレッジ文面編集",
      tab_simulator: "検索シミュレーター",
      tab_users: "ユーザー・権限管理",
      tab_audit: "操作監査ログ",
      tab_settings: "モデル・保守設定",
      lock_editor: "🔒 要編集権限",
      lock_admin: "🔒 要管理者",

      // Auth Gate Screen
      gate_title: "社内AIナレッジポータル",
      gate_subtitle: "LiteRT-LM ＆ Google Gemini ハイブリッド知識基盤",
      gate_badge: "🔒 ゼロトラスト企業認証ゲートウェイ (v4.2)",
      btn_google_sso: "Google Workspace アカウントでログイン",
      google_sso_sub: "※社内Workspaceドメイン（@company.com等）のGoogleアカウントでワンクリック認証",
      gate_divider: "または 社内ID/パスワードでログイン",
      lbl_user_id: "社員ユーザーID",
      ph_user_id: "例: admin_user または yamada_t",
      lbl_password: "パスワード",
      ph_password: "パスワードを入力",
      btn_login: "安全にログイン",
      demo_accounts_title: "💡 評価用アカウント一覧 (初期パスワード: password123):",
      demo_admin: "👑 最高管理者 (admin_user)",
      demo_editor: "✏️ ナレッジ編集長 (editor_user)",
      demo_viewer: "👤 一般閲覧社員 (viewer_user)",
      gate_notice: "※ログインしていない状態では、社内データおよび機能画面は一切開示されません（Strict Auth Guard）。",

      // Chat Tab
      btn_new_chat: "＋ 新しいチャット",
      history_header: "過去の会話履歴",
      btn_clear_all: "🗑️ 全ての会話履歴を削除",
      btn_history_list: "📜 履歴一覧",
      new_chat_title: "新しいチャット",
      btn_delete_chat: "この会話を削除",
      assistant_welcome: "こんにちは！社内規程、就業規則、経費精算、ガイドラインなどについて、何でもお気軽にご質問ください。<br>登録された全社内ドキュメント（Office、PDF、マニュアル等）に基づいて正確にお答えします。（※厳選出典リンク付き）",
      quick_chips_label: "よくある質問例:",
      chip_1: "通勤手当の上限額は？",
      chip_2: "リモートワークの条件は？",
      chip_3: "AIツールの利用基準は？",
      chip_4: "台湾の総理大臣は？",
      chat_placeholder: "質問を入力してください... (Shift+Enterで改行, Enterで送信)",
      btn_send: "送信",

      // Upload & Drive Tab
      drive_box_title: "☁️ Google Drive 常時ナレッジ自動同期",
      drive_box_badge: "Changes API 差分検知",
      drive_box_desc: "社内Google Drive上のドキュメント（Docs）、スプレッドシート（Sheets）、スライド（Slides）、PDF等を常時監視し、更新・新規・削除を自動検知してAI知識を最新化します。手動での2重作業や転記ミスを根絶します。",
      btn_sync_now: "🔄 今すぐDriveと同期 (Sync Now)",
      btn_drive_folders: "⚙️ 同期対象フォルダ設定",
      lbl_sync_status: "同期ステータス",
      lbl_last_sync: "最終同期日時",
      lbl_synced_files: "同期済みファイル数",
      lbl_gen_blocks: "生成ナレッジブロック数",
      upload_card_title: "📁 社内ドキュメントのマルチフォーマット一括登録（手動アップロード）",
      upload_card_desc: "Office全般（Word・Excel・PowerPoint）、PDF、テキストファイルをそのままドラッグ＆ドロップで登録できます。文書構造を自動認識し、「文境界優先チャンキング」により最適な知識ブロックへ分割・インデックス化されます。",
      dropzone_prompt: "あらゆる書類ファイルを選択またはドラッグ＆ドロップしてください",
      btn_select_file: "ファイルを選択",
      btn_upload_start: "このファイルを解析して知識ベースへ登録",
      btn_clear_file: "クリア",
      unselected_file: "未選択",

      // CMS Tab
      cms_card_title: "✏️ ナレッジ文面ブロック編集 (CMS)",
      cms_card_desc: "ファイル全体を再登録することなく、特定の条文や文章ブロックをブラウザ上で直接修正・削除できます。保存すると即座に再ベクトル化され、チャット回答にミリ秒単位で反映されます。",
      btn_new_block: "＋ 新しい文面を追加",
      cms_search_ph: "文面やタイトルで検索して絞り込み...",
      btn_refresh_blocks: "更新 🔄",

      // Simulator Tab
      sim_card_title: "🔍 検索シミュレーター (Fast Retrieval)",
      sim_card_desc: "ユーザーの質問に対して「どの文書のどの文面がヒットするか」を、LLMの回答生成を挟まずに1秒未満で直接テストします。修正した文面が意図通りに検索されるかの検証に最適です。",
      sim_search_ph: "検索キーワードまたは質問文を入力... (例: 交通費の上限)",
      btn_run_sim: "検索テスト実行",
      sim_initial_placeholder: "検索ボタンを押すと、ヒットした文面と類似度スコアがここに表示されます。",

      // User Mgmt Tab
      user_mgmt_title: "👥 社員アカウント＆権限ライフサイクル管理 (管理者・編集長専用)",
      user_mgmt_desc: "入社時のアカウント発行、人事異動に伴う権限変更・パスワード再発行、休職・退社時の即時利用停止や完全抹消を安全かつ確実に実行します。",
      btn_register_user: "＋ 新規社員アカウント登録",
      stat_total_users: "📋 登録社員総数",
      stat_active_users: "🟢 有効稼働アカウント",
      stat_suspended_users: "🔴 停止・休職中",
      stat_admin_users: "👑 システム管理者",
      user_search_ph: "社員名、ユーザーID、部署で検索...",
      opt_all_roles: "すべての役職",
      opt_admin_role: "システム管理者 (Admin)",
      opt_editor_role: "ナレッジ編集長 (Editor)",
      opt_viewer_role: "一般閲覧者 (Viewer)",
      opt_all_status: "すべての状態",
      opt_status_active: "🟢 有効のみ",
      opt_status_suspended: "🔴 停止中のみ",
      btn_filter_reset: "リセット",
      btn_refresh_users: "最新に更新 🔄",
      th_id: "ユーザーID",
      th_name: "社員名 (表示名)",
      th_dept: "所属部署",
      th_role: "付与役職",
      th_status: "アカウント状態",
      th_notes: "備考・メモ",
      th_actions: "安全操作",

      // Audit Tab
      audit_card_title: "📜 操作監査ログ & システム診断",
      audit_card_desc: "「誰が、いつ、どこから、どの操作を行ったか」の完全な監査証跡を記録・追跡します。システム障害時の詳細ログ・スタックトレースも確認できます。",
      btn_refresh_audit: "最新ログに更新 🔄",
      audit_user_ph: "ユーザーIDで絞り込み...",
      opt_all_actions: "すべての操作区分",
      btn_search_audit: "絞り込み検索 🔎",
      th_time: "発生日時",
      th_operator: "操作者",
      th_audit_role_col: "役職",
      th_action_type: "操作区分",
      th_target_res: "対象リソース",
      th_audit_status_col: "状態",
      th_summary: "詳細要約 (サニタイズ済)",
      th_ip: "IPアドレス",
      diagnostics_title: "🛠️ システム障害・エラー診断ログ (スタックトレース記録)",
      diagnostics_desc: "直近のシステム例外や内部エラーのスタックトレースおよびコンテキストを保持・表示します。",
      diagnostics_clean: "システムエラーは現在記録されていません（正常稼働中）。",

      // Settings & MCP Tab
      settings_card_title: "⚙️ 推論モデル & 保守設定 (管理者専用)",
      settings_card_desc: "推論プロバイダの切り替え、APIキー管理、およびログ保存期間（最大1年）の調整を行います。",
      prov_active_label: "アクティブ推論プロバイダ",
      prov_litert_t: "🍏 ローカル完全オフライン (LiteRT-LM)",
      prov_litert_d: "Apple Silicon Metal GPUで高速動作。外部インターネット通信ゼロ（パケット漏洩リスク0%）。",
      prov_gemini_t: "☁️ クラウド最新モデル (Google Gemini API)",
      prov_gemini_d: "Google公式SDK（無料枠Gemini 3.5 Flash Lite専用）。高度な思考と高速回答。",
      btn_discover: "🔄 公開中の利用可能モデル一覧を取得",
      retention_title: "📅 ログ保存期間設定 (監査・保守ポリシー)",
      retention_desc: "社内規程・法令遵守ポリシーに基づき、操作監査ログおよびシステム診断ログの保持期間を設定します。期限を過ぎたログは自動的にクリーンアップされます。",
      btn_save_all: "すべての設定を保存して反映 💾",
      mcp_card_title: "🔌 外部AI連携 MCP サーバー (Model Context Protocol)",
      btn_test_mcp: "⚡ MCP 疎通テスト実行",

      // Common Toasts & Dynamic Messages
      toast_auth_success: "認証成功！ ようこそ、{name}さん。",
      toast_auth_fail: "認証に失敗しました。ユーザーIDまたはパスワードをご確認ください。",
      toast_logout: "ログアウトしました。",
      toast_idle_timeout: "🔒 セッション有効期限切れ、または30分無操作のため自動ログアウトしました。再度ログインしてください。",
      toast_lockout: "⛔ 連続認証失敗のため、アカウントが5分間一時ロックされています。残り: {seconds}秒",
      toast_saved: "設定を保存しました。",
      toast_deleted: "削除を完了しました。",
      toast_sync_success: "Drive同期が正常に完了しました。",
      toast_copy_success: "クリップボードにコピーしました！"
    },

    en: {
      // Header & Navigation
      app_title: "Enterprise AI Knowledge Portal",
      app_subtitle: "LiteRT-LM & Google Gemini Hybrid Knowledge Engine (v4.2 Enterprise)",
      logged_in_as: "👤 Logged in:",
      btn_logout: "🚪 Logout",
      role_admin: "👑 Admin",
      role_editor: "✏️ Editor",
      role_viewer: "👤 Viewer",
      mode_local: "Local Inference (LiteRT-LM)",
      mode_cloud: "Cloud Inference (Google Gemini)",

      tab_chat: "AI Chat",
      tab_upload: "Document Upload",
      tab_cms: "Knowledge CMS",
      tab_simulator: "Retrieval Simulator",
      tab_users: "User & Role Mgmt",
      tab_audit: "Audit Logs",
      tab_settings: "Model Settings",
      lock_editor: "🔒 Editor Required",
      lock_admin: "🔒 Admin Required",

      // Auth Gate Screen
      gate_title: "Enterprise AI Knowledge Portal",
      gate_subtitle: "LiteRT-LM & Google Gemini Hybrid Knowledge Base",
      gate_badge: "🔒 Zero-Trust Enterprise Auth Gateway (v4.2)",
      btn_google_sso: "Login with Google Workspace",
      google_sso_sub: "* One-click login for corporate Workspace domain (@company.com, etc.)",
      gate_divider: "Or login with Employee ID & Password",
      lbl_user_id: "Employee User ID",
      ph_user_id: "e.g., admin_user or yamada_t",
      lbl_password: "Password",
      ph_password: "Enter your password",
      btn_login: "Secure Login",
      demo_accounts_title: "💡 Evaluation Accounts (Default Password: password123):",
      demo_admin: "👑 System Admin (admin_user)",
      demo_editor: "✏️ Knowledge Editor (editor_user)",
      demo_viewer: "👤 General Employee (viewer_user)",
      gate_notice: "* Corporate data and features are strictly protected until authenticated (Strict Auth Guard).",

      // Chat Tab
      btn_new_chat: "＋ New Chat",
      history_header: "Conversation History",
      btn_clear_all: "🗑️ Clear All History",
      btn_history_list: "📜 History",
      new_chat_title: "New Chat",
      btn_delete_chat: "Delete Chat",
      assistant_welcome: "Hello! Feel free to ask anything about company policies, regulations, expense claims, or operational guidelines.<br>Accurate answers based strictly on all registered company documents (Office, PDF, manuals).",
      quick_chips_label: "Suggested Questions:",
      chip_1: "Commuter allowance limit?",
      chip_2: "Remote work conditions?",
      chip_3: "AI tool usage guidelines?",
      chip_4: "Prime Minister of Taiwan?",
      chat_placeholder: "Type your question... (Shift+Enter for newline, Enter to send)",
      btn_send: "Send",

      // Upload & Drive Tab
      drive_box_title: "☁️ Google Drive Continuous Knowledge Sync",
      drive_box_badge: "Changes API Differential Detection",
      drive_box_desc: "Monitors Google Docs, Sheets, Slides, and PDFs on corporate Google Drive. Automatically detects updates, additions, and deletions to keep AI knowledge up to date.",
      btn_sync_now: "🔄 Sync Now",
      btn_drive_folders: "⚙️ Sync Folder Settings",
      lbl_sync_status: "Sync Status",
      lbl_last_sync: "Last Sync Time",
      lbl_synced_files: "Synced Files",
      lbl_gen_blocks: "Knowledge Blocks Generated",
      upload_card_title: "📁 Multi-Format Document Ingestion (Manual Upload)",
      upload_card_desc: "Upload Word, Excel, PowerPoint, PDF, and text files directly via drag & drop. Parsed and indexed automatically using sentence-boundary chunking.",
      dropzone_prompt: "Select or drag & drop any document file here",
      btn_select_file: "Select File",
      btn_upload_start: "Parse & Import File",
      btn_clear_file: "Clear",
      unselected_file: "No file selected",

      // CMS Tab
      cms_card_title: "✏️ Knowledge Block Editor (CMS)",
      cms_card_desc: "Edit or delete specific content blocks directly in your browser without re-uploading files. Changes are instantly re-vectorized for immediate retrieval.",
      btn_new_block: "＋ Add New Block",
      cms_search_ph: "Search by content or title...",
      btn_refresh_blocks: "Refresh 🔄",

      // Simulator Tab
      sim_card_title: "🔍 Fast Retrieval Simulator",
      sim_card_desc: "Test vector search hits under 1 second without LLM generation. Ideal for verifying modified knowledge blocks.",
      sim_search_ph: "Enter search keywords or query... (e.g. travel expense)",
      btn_run_sim: "Run Search Test",
      sim_initial_placeholder: "Matching blocks and similarity scores will appear here after running a search.",

      // User Mgmt Tab
      user_mgmt_title: "👥 Employee Account & RBAC Lifecycle Management",
      user_mgmt_desc: "Manage employee onboarding, role promotion, password resets, suspensions, and safe deletions.",
      btn_register_user: "＋ Register New Employee",
      stat_total_users: "📋 Total Employees",
      stat_active_users: "🟢 Active Accounts",
      stat_suspended_users: "🔴 Suspended",
      stat_admin_users: "👑 System Admins",
      user_search_ph: "Search by name, ID, or department...",
      opt_all_roles: "All Roles",
      opt_admin_role: "System Admin (Admin)",
      opt_editor_role: "Knowledge Editor (Editor)",
      opt_viewer_role: "General Viewer (Viewer)",
      opt_all_status: "All Statuses",
      opt_status_active: "🟢 Active Only",
      opt_status_suspended: "🔴 Suspended Only",
      btn_filter_reset: "Reset",
      btn_refresh_users: "Refresh List 🔄",
      th_id: "User ID",
      th_name: "Employee Name",
      th_dept: "Department",
      th_role: "Assigned Role",
      th_status: "Account Status",
      th_notes: "Notes",
      th_actions: "Actions",

      // Audit Tab
      audit_card_title: "📜 Audit Trail & System Diagnostics",
      audit_card_desc: "Tracks comprehensive audit logs (who, when, IP, action). Also inspect system exception stacktraces.",
      btn_refresh_audit: "Refresh Audit Logs 🔄",
      audit_user_ph: "Filter by User ID...",
      opt_all_actions: "All Action Types",
      btn_search_audit: "Search 🔎",
      th_time: "Timestamp",
      th_operator: "Operator",
      th_audit_role_col: "Role",
      th_action_type: "Action Type",
      th_target_res: "Target Resource",
      th_audit_status_col: "Status",
      th_summary: "Sanitized Summary",
      th_ip: "IP Address",
      diagnostics_title: "🛠️ System Error Diagnostics (Stacktraces)",
      diagnostics_desc: "Retains and displays recent system exception stacktraces and execution contexts.",
      diagnostics_clean: "No system errors currently recorded (System operational).",

      // Settings & MCP Tab
      settings_card_title: "⚙️ Inference Model & Maintenance Settings (Admin Only)",
      settings_card_desc: "Configure inference providers, API keys, and log retention period (up to 1 year).",
      prov_active_label: "Active Inference Provider",
      prov_litert_t: "🍏 Fully Offline Local (LiteRT-LM)",
      prov_litert_d: "High-speed execution on Apple Silicon Metal GPU. Zero external network traffic (0% data leak risk).",
      prov_gemini_t: "☁️ Cloud Latest Models (Google Gemini API)",
      prov_gemini_d: "Official Google GenAI SDK (Optimized for free-tier Gemini 3.5 Flash Lite). High-speed reasoning.",
      btn_discover: "🔄 Discover Live Gemini Models",
      retention_title: "📅 Log Retention Policy",
      retention_desc: "Configure retention period for audit and diagnostic logs. Expired logs are automatically purged.",
      btn_save_all: "Save & Apply All Settings 💾",
      mcp_card_title: "🔌 External AI Integration MCP Server (Model Context Protocol)",
      btn_test_mcp: "⚡ Test MCP Connection",

      // Common Toasts & Dynamic Messages
      toast_auth_success: "Authentication successful! Welcome, {name}.",
      toast_auth_fail: "Authentication failed. Please check your user ID or password.",
      toast_logout: "Logged out successfully.",
      toast_idle_timeout: "🔒 Auto logged out due to session expiration or 30 mins of inactivity. Please log in again.",
      toast_lockout: "⛔ Account temporarily locked for 5 minutes due to consecutive failed attempts. Remaining: {seconds}s",
      toast_saved: "Settings saved successfully.",
      toast_deleted: "Deleted successfully.",
      toast_sync_success: "Google Drive sync completed successfully.",
      toast_copy_success: "Copied to clipboard!"
    },

    'zh-TW': {
      // Header & Navigation
      app_title: "企業 AI 知識門戶",
      app_subtitle: "LiteRT-LM 與 Google Gemini 混合知識基建 (v4.2 Enterprise)",
      logged_in_as: "👤 已登入:",
      btn_logout: "🚪 登出",
      role_admin: "👑 管理員",
      role_editor: "✏️ 主編",
      role_viewer: "👤 檢視者",
      mode_local: "本機推理 (LiteRT-LM)",
      mode_cloud: "雲端推理 (Google Gemini)",

      tab_chat: "企業對話",
      tab_upload: "文件資料批量匯入",
      tab_cms: "知識條文編輯 (CMS)",
      tab_simulator: "檢索模擬器",
      tab_users: "使用者與權限管理",
      tab_audit: "操作審計日誌",
      tab_settings: "模型與維護設定",
      lock_editor: "🔒 需編輯權限",
      lock_admin: "🔒 需管理員",

      // Auth Gate Screen
      gate_title: "企業 AI 知識門戶",
      gate_subtitle: "LiteRT-LM 與 Google Gemini 混合知識基建",
      gate_badge: "🔒 零信任企業認證閘道器 (v4.2)",
      btn_google_sso: "使用 Google Workspace 帳號登入",
      google_sso_sub: "※ 使用企業 Workspace 網域（@company.com 等）Google 帳號一鍵認證",
      gate_divider: "或 使用企業帳號與密碼登入",
      lbl_user_id: "員工帳號 ID",
      ph_user_id: "例如: admin_user 或 yamada_t",
      lbl_password: "密碼",
      ph_password: "請輸入密碼",
      btn_login: "安全登入",
      demo_accounts_title: "💡 評估用帳號列表 (預設密碼: password123):",
      demo_admin: "👑 最高管理員 (admin_user)",
      demo_editor: "✏️ 知識主編 (editor_user)",
      demo_viewer: "👤 一般員工 (viewer_user)",
      gate_notice: "※ 未登入狀態下，企業資料與功能頁面一律不予公開（Strict Auth Guard）。",

      // Chat Tab
      btn_new_chat: "＋ 新增對話",
      history_header: "對話歷史記錄",
      btn_clear_all: "🗑️ 清除所有對話記錄",
      btn_history_list: "📜 歷史記錄",
      new_chat_title: "新對話",
      btn_delete_chat: "刪除此對話",
      assistant_welcome: "您好！歡迎詢問有關公司規章、工作規則、報銷流程、指導方針等任何問題。<br>系統將基於所有已匯入的企業文件（Office、PDF、手冊等）進行精確解答。（※附嚴選引用來源）",
      quick_chips_label: "常見提問範例:",
      chip_1: "交通津貼上限金額？",
      chip_2: "遠端工作申請條件？",
      chip_3: "AI 工具使用規範？",
      chip_4: "台灣的行政院長是？",
      chat_placeholder: "請輸入您的提問... (Shift+Enter 換行，Enter 發送)",
      btn_send: "發送",

      // Upload & Drive Tab
      drive_box_title: "☁️ Google Drive 常態知識自動同步",
      drive_box_badge: "Changes API 差異偵測",
      drive_box_desc: "即時監控企業 Google Drive 上的文件 (Docs)、表格 (Sheets)、簡報 (Slides)、PDF 等，自動偵測更新、新增與刪除，確保 AI 知識保持最新狀態。",
      btn_sync_now: "🔄 立即與 Drive 同步",
      btn_drive_folders: "⚙️ 設定同步資料夾",
      lbl_sync_status: "同步狀態",
      lbl_last_sync: "上次同步時間",
      lbl_synced_files: "已同步檔案數",
      lbl_gen_blocks: "生成知識條文數",
      upload_card_title: "📁 企業文件多格式批量匯入（手動上傳）",
      upload_card_desc: "可直接拖放匯入 Office 文件（Word、Excel、PowerPoint）、PDF 及文字檔。系統將自動識別結構並進行文句邊界區塊化與索引。",
      dropzone_prompt: "請選擇或拖放任何文件檔案至此處",
      btn_select_file: "選擇檔案",
      btn_upload_start: "解析此檔案並匯入知識庫",
      btn_clear_file: "清除",
      unselected_file: "未選擇檔案",

      // CMS Tab
      cms_card_title: "✏️ 知識條文區塊編輯 (CMS)",
      cms_card_desc: "無需重新匯入整份檔案，即可在瀏覽器上直接修改或刪除特定條文。儲存後立即重新向量化並反映於對話解答中。",
      btn_new_block: "＋ 新增知識條文",
      cms_search_ph: "搜尋條文內容或標題...",
      btn_refresh_blocks: "更新 🔄",

      // Simulator Tab
      sim_card_title: "🔍 檢索模擬器 (Fast Retrieval)",
      sim_card_desc: "不經由 LLM 生成回應，在 1 秒內直接測試與提問比對成功的條文。非常適合驗證修改後的條文檢索效果。",
      sim_search_ph: "請輸入搜尋關鍵字或提問... (例如: 交通費上限)",
      btn_run_sim: "執行檢索測試",
      sim_initial_placeholder: "點擊搜尋按鈕後，比對成功的條文與相似度分數將顯示於此。",

      // User Mgmt Tab
      user_mgmt_title: "👥 員工帳號與權限生命週期管理",
      user_mgmt_desc: "安全確實地執行入職開戶、異動調職權限變更、密碼重設、停職與離職解約等完整流程。",
      btn_register_user: "＋ 新增員工帳號",
      stat_total_users: "📋 註冊員工總數",
      stat_active_users: "🟢 正常使用帳號",
      stat_suspended_users: "🔴 已停用/休職",
      stat_admin_users: "👑 系統管理員",
      user_search_ph: "搜尋姓名、帳號 ID、部門...",
      opt_all_roles: "所有職務",
      opt_admin_role: "系統管理員 (Admin)",
      opt_editor_role: "知識主編 (Editor)",
      opt_viewer_role: "一般檢視者 (Viewer)",
      opt_all_status: "所有狀態",
      opt_status_active: "🟢 僅顯示正常",
      opt_status_suspended: "🔴 僅顯示停用",
      btn_filter_reset: "重設",
      btn_refresh_users: "最新更新 🔄",
      th_id: "帳號 ID",
      th_name: "姓名 (顯示名稱)",
      th_dept: "所屬部門",
      th_role: "獲賦職務",
      th_status: "帳號狀態",
      th_notes: "備註",
      th_actions: "安全操作",

      // Audit Tab
      audit_card_title: "📜 操作審計日誌與系統診斷",
      audit_card_desc: "完整記錄與追蹤「何人、何時、自何處 IP 執行何種操作」。並可檢視系統異常時的詳細日誌與堆疊追蹤。",
      btn_refresh_audit: "更新最新日誌 🔄",
      audit_user_ph: "依帳號 ID 篩選...",
      opt_all_actions: "所有操作類別",
      btn_search_audit: "篩選搜尋 🔎",
      th_time: "發生時間",
      th_operator: "操作者",
      th_audit_role_col: "職務",
      th_action_type: "操作類別",
      th_target_res: "目標資源",
      th_audit_status_col: "狀態",
      th_summary: "詳細摘要 (已脫敏)",
      th_ip: "IP 位址",
      diagnostics_title: "🛠️ 系統異常與錯誤診斷日誌 (堆疊追蹤紀錄)",
      diagnostics_desc: "保存並顯示最近系統例外或內部錯誤的堆疊追蹤與情境。",
      diagnostics_clean: "目前無系統錯誤紀錄（系統正常運作中）。",

      // Settings & MCP Tab
      settings_card_title: "⚙️ 推理模型與維護設定 (管理員專用)",
      settings_card_desc: "切換推理供應商、管理 API 金鑰以及調整日誌保存期限（最長 1 年）。",
      prov_active_label: "目前使用中推理供應商",
      prov_litert_t: "🍏 本機完全離線 (LiteRT-LM)",
      prov_litert_d: "於 Apple Silicon Metal GPU 高速執行。零外部網路傳輸（封包洩漏風險 0%）。",
      prov_gemini_t: "☁️ 雲端最新模型 (Google Gemini API)",
      prov_gemini_d: "Google 官方 SDK（支援免費額度 Gemini 3.5 Flash Lite）。具備深度思考與快速回應能力。",
      btn_discover: "🔄 取得公開可用模型列表",
      retention_title: "📅 日誌保存期限設定 (審計與維護策略)",
      retention_desc: "依據企業規章與合規策略設定操作審計與系統診斷日誌之保存期限。逾期日誌將自動清除。",
      btn_save_all: "儲存並套用所有設定 💾",
      mcp_card_title: "🔌 外部 AI 連動 MCP 伺服器 (Model Context Protocol)",
      btn_test_mcp: "⚡ 執行 MCP 連通測試",

      // Common Toasts & Dynamic Messages
      toast_auth_success: "認證成功！歡迎，{name}。",
      toast_auth_fail: "認證失敗，請檢查您的帳號 ID 或密碼。",
      toast_logout: "已成功登出。",
      toast_idle_timeout: "🔒 因超過 30 分鐘無操作或會話過期，系統已自動登出。請重新登入。",
      toast_lockout: "⛔ 由於連續輸入錯誤密碼，帳號已暫時鎖定 5 分鐘。剩餘時間: {seconds} 秒",
      toast_saved: "設定已成功儲存。",
      toast_deleted: "已成功刪除。",
      toast_sync_success: "Google Drive 同步處理已成功完成。",
      toast_copy_success: "已複製至剪貼簿！"
    }
  };

  Object.assign(translations.ja, {
    guide_join_html: "「<strong>＋ 新規社員アカウント登録</strong>」をクリック。社員ID・氏名・部署・初期役職（Viewer推奨）を設定し、初期パスワードを発行します。完了後に発行される初期ログイン案内文をコピーして本人に通知します。",
    guide_transfer_html: "対象社員の「<strong>✏️ 編集</strong>」から役職（Editorへの昇格など）や所属部署を即座に変更。パスワード忘れ時には「<strong>🔑 PWリセット</strong>」で安全に初期化できます。",
    guide_leave_html: "「<strong>🛑 利用停止</strong>」を押すことで、過去の監査証跡を残したまま即座にログイン遮断＆セッションを強制切断します（推奨）。完全に抹消する場合は「<strong>🗑️ 削除</strong>」を実行します（自己削除・最終Admin保護機能付き）。",
    mcp_desc_html: "本社内ナレッジポータルは、Anthropic社提唱の業界標準プロトコル <strong>Model Context Protocol (MCP)</strong> サーバーをネイティブ標準搭載しています。Claude Desktop や Cursor、自律コーディングエージェント等の外部AIツールから、社内ナレッジ（ベクトル検索・条文取得）を外部ツールとしてシームレスに直接呼び出すことができます。",
    mcp_cfg_html: "<code>claude_desktop_config.json</code> に以下の設定を追加すると、Claude から直接本社内ナレッジを検索・参照できるようになります:"
  });
  Object.assign(translations.en, {
    guide_join_html: "Click \"<strong>＋ Register New Employee</strong>\". Set employee ID, name, department and initial role (Viewer recommended), then issue an initial password. Copy the welcome message issued afterwards and send it to the employee.",
    guide_transfer_html: "Use \"<strong>✏️ Edit</strong>\" on the employee to change role (e.g. promote to Editor) or department instantly. If the password is forgotten, safely reinitialize it with \"<strong>🔑 Reset PW</strong>\".",
    guide_leave_html: "Pressing \"<strong>🛑 Suspend</strong>\" instantly blocks login and force-disconnects sessions while keeping past audit trails (recommended). To remove permanently, use \"<strong>🗑️ Delete</strong>\" (with self-deletion and last-Admin protection).",
    mcp_desc_html: "This portal natively ships a <strong>Model Context Protocol (MCP)</strong> server, the industry-standard protocol proposed by Anthropic. External AI tools such as Claude Desktop, Cursor and autonomous coding agents can directly call internal knowledge (vector search and clause retrieval) as external tools.",
    mcp_cfg_html: "Add the following to <code>claude_desktop_config.json</code> so Claude can search and reference internal knowledge directly:"
  });
  Object.assign(translations['zh-TW'], {
    guide_join_html: "點擊「<strong>＋ 新增員工帳號</strong>」，設定員工 ID、姓名、部門與初始職務（建議 Viewer）並發放初始密碼。完成後複製所產生的初始登入通知並通知本人。",
    guide_transfer_html: "由該員工的「<strong>✏️ 編輯</strong>」立即變更職務（如升為 Editor）或所屬部門。忘記密碼時，可用「<strong>🔑 重設密碼</strong>」安全地重新初始化。",
    guide_leave_html: "按下「<strong>🛑 停用</strong>」即可在保留過去審計軌跡的情況下，立即阻斷登入並強制中斷工作階段（建議）。若要完全刪除，請執行「<strong>🗑️ 刪除</strong>」（具備防止自我刪除與保護最後一位 Admin 的機制）。",
    mcp_desc_html: "本企業知識門戶原生內建由 Anthropic 提出的業界標準協定 <strong>Model Context Protocol (MCP)</strong> 伺服器。Claude Desktop、Cursor、自主程式設計代理等外部 AI 工具，可將企業知識（向量搜尋・條文取得）作為外部工具無縫直接呼叫。",
    mcp_cfg_html: "將以下設定加入 <code>claude_desktop_config.json</code>，Claude 即可直接搜尋並參照企業知識:"
  });

  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'PRE', 'CODE', 'NOSCRIPT']);
  const JA_RE = /[\u3040-\u30ff\u4e00-\u9fff]/;

  class I18nEngine {
    constructor() {
      const saved = localStorage.getItem(STORAGE_KEY);
      this.currentLang = saved && translations[saved] ? saved : 'ja';
      this.dict = translations;
      this._nodeRec = new WeakMap();   // text node -> {orig, shown}
      this._observer = null;
      this._busy = false;
    }

    _idx() { return this.currentLang === 'en' ? 0 : 1; }

    t(key, params = {}) {
      const langDict = translations[this.currentLang] || translations.ja;
      let text = langDict[key] || translations.ja[key] || key;
      if (typeof text === 'string') {
        Object.keys(params).forEach(p => {
          text = text.replace(new RegExp(`\\{${p}\\}`, 'g'), params[p]);
        });
      }
      return text;
    }

    /** Translate an arbitrary Japanese UI string via phrase table / patterns. Returns input if no match. */
    tr(text) {
      if (this.currentLang === 'ja' || typeof text !== 'string' || !JA_RE.test(text)) return text;
      const lead = text.match(/^\s*/)[0];
      const trail = text.match(/\s*$/)[0];
      const core = text.trim();
      const phrases = window.I18N_PHRASES || {};
      const norm = core.replace(/\s+/g, ' ');
      const i = this._idx();
      if (!this._rev) {
        this._rev = {};
        Object.keys(translations.ja).forEach(k => {
          const v = String(translations.ja[k]);
          if (v.indexOf('{') >= 0 || v.indexOf('<') >= 0) return;
          this._rev[v.replace(/\s+/g, ' ').trim()] = k;
        });
      }
      if (phrases[core]) return lead + phrases[core][i] + trail;
      if (this._rev[norm] && !phrases[norm]) {
        const dv = translations[this.currentLang][this._rev[norm]];
        if (dv) return lead + dv + trail;
      }
      if (phrases[norm]) return lead + phrases[norm][i] + trail;
      for (const [re, en, zh] of (window.I18N_PATTERNS || [])) {
        const m = core.match(re);
        if (m) {
          const tpl = i === 0 ? en : zh;
          return lead + tpl.replace(/\$(\d)/g, (_, n) => {
            const v = m[Number(n)] === undefined ? '' : m[Number(n)];
            return this.tr(v);
          }) + trail;
        }
      }
      return text;
    }

    setLanguage(lang) {
      if (!translations[lang]) return;
      this.currentLang = lang;
      localStorage.setItem(STORAGE_KEY, lang);
      document.documentElement.lang = lang;
      this.updateDOM();
      window.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang } }));
    }

    _processTextNode(node) {
      const p = node.parentElement;
      if (!p || SKIP_TAGS.has(p.tagName) || p.closest('[data-i18n],[data-i18n-html]')) return;
      let rec = this._nodeRec.get(node);
      const cur = node.nodeValue;
      let orig;
      if (rec && cur === rec.shown) orig = rec.orig; else orig = cur;
      if (!JA_RE.test(orig)) { if (rec) this._nodeRec.delete(node); return; }
      const shown = this.tr(orig);
      this._nodeRec.set(node, { orig, shown });
      if (shown !== cur) node.nodeValue = shown;
    }

    _processAttrs(el) {
      if (SKIP_TAGS.has(el.tagName) && el.tagName !== 'TEXTAREA') return;
      ['placeholder', 'title'].forEach(attr => {
        if (el.hasAttribute('data-i18n-' + attr)) return;
        const v = el.getAttribute(attr);
        if (v === null) return;
        const oAttr = 'data-i18n-o-' + attr, sAttr = 'data-i18n-s-' + attr;
        let orig = (el.getAttribute(sAttr) === v && el.hasAttribute(oAttr)) ? el.getAttribute(oAttr) : v;
        if (!JA_RE.test(orig)) return;
        const shown = this.tr(orig);
        el.setAttribute(oAttr, orig);
        el.setAttribute(sAttr, shown);
        if (shown !== v) el.setAttribute(attr, shown);
      });
    }

    _processTree(root) {
      if (!root) return;
      if (root.nodeType === Node.TEXT_NODE) { this._processTextNode(root); return; }
      if (root.nodeType !== Node.ELEMENT_NODE) return;
      this._processAttrs(root);
      root.querySelectorAll('[placeholder],[title]').forEach(el => this._processAttrs(el));
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(n => this._processTextNode(n));
    }

    _startObserver() {
      if (this._observer || !document.body) return;
      this._observer = new MutationObserver(muts => {
        if (this._busy) return;
        this._busy = true;
        try {
          muts.forEach(m => {
            if (m.type === 'characterData') this._processTextNode(m.target);
            else if (m.type === 'attributes') this._processAttrs(m.target);
            else m.addedNodes.forEach(n => this._processTree(n));
          });
        } finally { this._busy = false; }
      });
      this._observer.observe(document.body, {
        childList: true, subtree: true, characterData: true,
        attributes: true, attributeFilter: ['placeholder', 'title']
      });
    }

    updateDOM() {
      this._busy = true;
      try {
        document.querySelectorAll('[data-i18n]').forEach(el => {
          const key = el.getAttribute('data-i18n');
          if (key) el.textContent = this.t(key);
        });
        document.querySelectorAll('[data-i18n-html]').forEach(el => {
          const key = el.getAttribute('data-i18n-html');
          if (key) el.innerHTML = this.t(key);
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
          const key = el.getAttribute('data-i18n-placeholder');
          if (key) el.placeholder = this.t(key);
        });
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
          const key = el.getAttribute('data-i18n-title');
          if (key) el.title = this.t(key);
        });
        this._processTree(document.body);
        document.title = this.t('app_title');
        const selector = document.getElementById('lang-selector');
        if (selector && selector.value !== this.currentLang) selector.value = this.currentLang;
      } finally { this._busy = false; }
      this._startObserver();
    }
  }

  window.i18n = new I18nEngine();

  // Translate native confirm()/alert() dialogs
  const _confirm = window.confirm.bind(window);
  window.confirm = (msg) => _confirm(window.i18n.tr(msg));
  const _alert = window.alert.bind(window);
  window.alert = (msg) => _alert(window.i18n.tr(String(msg)));
})();
