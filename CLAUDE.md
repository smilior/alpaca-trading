# Alpaca Trading AI Agent Project

## プロジェクト概要

Alpaca APIを使った米国株の自動売買システム。cron + Claude CLIで自律的に動作するAIエージェントが市場を分析し、売買判断・執行を行う。まずペーパートレーディングで戦略を検証し、移行基準を満たしたらリアルマネーへ移行する。

## 現在のフェーズ: Phase 5（ペーパートレーディング運用）準備完了

Phase 1〜4 の開発が完了。次のステップはペーパートレーディング環境での試運転。

### 完了済みフェーズ

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 1 | 環境構築・基盤整備（config, DB, logging, types） | 完了 |
| Phase 2 | データ収集・シグナル実装（market data, LLM analyzer, technical filters） | 完了 |
| Phase 3 | リスク管理・注文実行（order executor, risk manager, state manager, main loop） | 完了 |
| Phase 4 | 統合・テスト（health checks, backtest, stress test, launchd, integration tests） | 完了 |

### 品質指標

- テスト: 292件パス、カバレッジ92%
- lint: `ruff check . && ruff format --check .` エラーなし
- 型: `mypy --strict modules/types.py` エラーなし

### 主要ファイル一覧

| ファイル | 内容 |
|---------|------|
| `main.py` | オーケストレーター（morning/midday/eod/health_check 4モード、ファイルロック、冪等性3層） |
| `modules/types.py` | dataclasses + Protocol（BarData, PortfolioState, TradingDecision等） |
| `modules/config.py` | pydantic-settings AppConfig（config.toml + .env バリデーション） |
| `modules/db.py` | SQLite WAL初期化、9テーブルDDL、マイグレーション管理 |
| `modules/logger.py` | JSON Lines、RotatingFileHandler（10MB x 5世代） |
| `modules/data_collector.py` | Alpaca Market Data APIからOHLCV取得 + テクニカル指標計算 |
| `modules/llm_analyzer.py` | Claude CLI連携、JSON Schema Validation、フォールバック戦略 |
| `modules/technical.py` | SMA, RSI, ATR, 出来高比率、エントリーフィルター |
| `modules/macro.py` | マクロレジーム判定（SPY vs 200日MA + VIX、2変数MVP） |
| `modules/universe.py` | S&P500大型株30銘柄ユニバース |
| `modules/order_executor.py` | ブラケット注文（limit entry + stop-limit SL + limit TP） |
| `modules/risk_manager.py` | 4段階サーキットブレーカー、ポジションサイジング、セクター集中チェック |
| `modules/state_manager.py` | Alpaca API ↔ SQLite 同期、リコンシリエーション、ポジションCRUD |
| `modules/health.py` | 包括的ヘルスチェック（7項目: DB, API, 実行鮮度, CB, エラー, ディスク） |
| `modules/backtest.py` | PurgedTimeSeriesSplit、Sharpe/Sortino/max DD、ブートストラップCI |
| `modules/stress_test.py` | 5シナリオストレステスト（COVID-19, インフレ, SVB, 円キャリー, フラッシュクラッシュ） |
| `config.toml` | 全パラメータ（strategy/risk/macro/system/alpaca/alerts） |
| `deploy/launchd/` | 4 plist + setup.sh（DST対応、スリープ復帰対応） |

### データスキーマ（9テーブル）

positions, trades, daily_snapshots, execution_logs, circuit_breaker, strategy_params, reconciliation_logs, metrics, schema_version — 詳細DDLは `docs/phase1-technical-spec.md` セクション5参照。

## 成果物（docs/）

| ドキュメント | パス | 内容 |
|-------------|------|------|
| トレーディング戦略 | `docs/strategy.md` | 戦略概要・対象銘柄・エントリー/エグジット条件・目標リターン |
| システム設計書 | `docs/system-design.md` | アーキテクチャ・cronフロー・状態管理・エラーハンドリング |
| 企画議論ログ | `docs/planning-log.md` | 5人のAIエージェントチームによる企画プロセスの全記録 |
| アクションプラン | `docs/action-plan.md` | タスクリスト・優先順位・リアル移行基準 |
| Phase 1技術仕様書 | `docs/phase1-technical-spec.md` | データスキーマ・APIインターフェース・ディレクトリ構成 |

## スキル（.claude/skills/）

タスクに応じて該当スキルのSKILL.mdを読み込み、指示に従うこと。詳細はreferences/を参照。

| スキル | パス | 使うタイミング |
|--------|------|---------------|
| ビジネスフレームワーク | `.claude/skills/business-frameworks/` | 企画・戦略立案・仮説検証 |
| 構造化ディベート | `.claude/skills/structured-debate/` | 複数案の比較・意思決定・反論が必要なとき |
| 米国株リサーチ | `.claude/skills/us-stock-research/` | 市場調査・セクター分析・銘柄スクリーニング |
| クオンツ戦略設計 | `.claude/skills/quant-strategy-design/` | 売買シグナル・バックテスト・戦略設計 |
| リスク管理 | `.claude/skills/risk-management/` | ポジションサイズ・ストップロス・ドローダウン管理 |
| Alpaca API | `.claude/skills/alpaca-api/` | Alpaca APIを使うコードの実装・レビュー |
| Claude CLIエージェント | `.claude/skills/claude-cli-agent/` | cron定期実行・自動化パイプライン構築 |
| 状態管理 | `.claude/skills/trading-state-management/` | DB設計・ポジション管理・取引履歴保存 |
| パフォーマンス評価 | `.claude/skills/performance-evaluation/` | KPI計測・レポート作成・ベンチマーク比較 |
| 戦略改善サイクル | `.claude/skills/strategy-improvement-cycle/` | 振り返り・パラメータ調整・リアル移行判定 |

## プラグイン（インストール済み）

| プラグイン | 用途 |
|-----------|------|
| pyright-lsp | Python静的型チェック。pydantic/dataclassesの型エラーをリアルタイム検出 |
| security-guidance | セキュリティ警告。APIキーハードコード・unsafe SQLパターンを防止 |
| feature-dev | 構造化開発ワークフロー（探索→設計→実装→レビュー） |
| claude-md-management | CLAUDE.mdの監査・更新管理 |
| code-review | PRレビュー。CLAUDE.mdルール準拠チェック |
| hookify | 危険操作ガードレール（.envコミット防止等） |
| code-simplifier | コード品質改善・簡素化 |
| commit-commands | コミット・プッシュ・PR作成 |

## 絶対ルール

- **ペーパー優先**: デフォルトは常にペーパートレーディング。リアル切替は明示的な指示がある場合のみ
- **リスク管理必須**: 売買コードには必ずストップロスを含める。リスク管理スキルを参照
- **APIキー保護**: ハードコード禁止。環境変数で管理し、.envは.gitignoreに含める
- **1変数ずつ**: 戦略改善時にパラメータを複数同時に変更しない

## 技術スタック

- Python 3.11+ / alpaca-py SDK / SQLite（WALモード）
- pydantic-settings（config.tomlバリデーション）
- pytest + ruff + mypy（開発ツール）
- numpy（バックテスト・統計計算）
- Claude CLI（cron/launchd定期実行）
- データ: Alpaca Market Data, yfinance, FRED API
- デプロイ: macOS launchd（`deploy/launchd/setup.sh` でインストール）
