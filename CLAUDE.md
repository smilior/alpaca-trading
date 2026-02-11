# Alpaca Trading AI Agent Project

## プロジェクト概要

Alpaca APIを使った米国株の自動売買システム。cron + Claude CLIで自律的に動作するAIエージェントが市場を分析し、売買判断・執行を行う。まずペーパートレーディングで戦略を検証し、移行基準を満たしたらリアルマネーへ移行する。

## 成果物（docs/）

| ドキュメント | パス | 内容 |
|-------------|------|------|
| トレーディング戦略 | `docs/strategy.md` | 戦略概要・対象銘柄・エントリー/エグジット条件・目標リターン |
| システム設計書 | `docs/system-design.md` | アーキテクチャ・cronフロー・状態管理・エラーハンドリング |
| 企画議論ログ | `docs/planning-log.md` | 5人のAIエージェントチームによる企画プロセスの全記録 |
| アクションプラン | `docs/action-plan.md` | タスクリスト・優先順位・リアル移行基準 |

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

## 絶対ルール

- **ペーパー優先**: デフォルトは常にペーパートレーディング。リアル切替は明示的な指示がある場合のみ
- **リスク管理必須**: 売買コードには必ずストップロスを含める。リスク管理スキルを参照
- **APIキー保護**: ハードコード禁止。環境変数で管理し、.envは.gitignoreに含める
- **1変数ずつ**: 戦略改善時にパラメータを複数同時に変更しない

## 技術スタック

- Python 3 / alpaca-py SDK / SQLite
- Claude CLI（cron定期実行）
- データ: Alpaca Market Data, yfinance, FRED API
