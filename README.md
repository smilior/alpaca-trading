# Alpaca Trading AI Agent

Alpaca API + Claude CLI で自律的に動作する米国株自動売買システム。
LLMセンチメント分析をプライマリシグナル、テクニカル指標をフィルターとするハイブリッドスイングトレード戦略を、macOS launchd で日次自動実行する。

## 仕組みの概要

```
┌─────────────────────────────────────────────────────┐
│  macOS launchd (cron)                               │
│  morning / midday / eod / health_check の4スケジュール│
└──────────────┬──────────────────────────────────────┘
               ▼
┌──────────────────────────┐
│  main.py (Orchestrator)  │
│  ・ファイルロック(排他制御)│
│  ・execution_id(冪等性)   │
│  ・client_order_id(重複防止)│
└──────────┬───────────────┘
           ▼
┌──────────────────────────────────────────────────────┐
│                  Pipeline                            │
│                                                      │
│  1. Config読込 + DB接続                               │
│  2. Reconciliation (Alpaca API ↔ SQLite同期)          │
│  3. マクロレジーム判定 (SPY vs 200日MA + VIX)           │
│  4. 市場データ収集 (OHLCV + テクニカル指標)              │
│  5. LLM分析 (Claude CLI → JSON決定)                   │
│  6. リスクフィルタリング (サーキットブレーカー/集中度)     │
│  7. 注文執行 (ブラケット注文: limit + SL + TP)          │
│  8. 状態保存 + ログ記録                                │
└──────────────────────────────────────────────────────┘
```

### 実行モード

| モード | スケジュール | 処理内容 |
|--------|-------------|---------|
| `morning` | 市場オープン後 | 全銘柄分析 → LLM売買判断 → 注文執行 |
| `midday` | 日中 | ポジション監視 + 市場データ更新 |
| `eod` | 引け後 | 日次スナップショット保存、パフォーマンス記録 |
| `health_check` | 定期 | DB・API・ディスク等7項目のヘルスチェック |
| `preflight` | 手動 | 起動前の全項目チェック（初回セットアップ確認） |
| `report` | 手動 | 口座情報・トレード統計・ドローダウン表示 |

### 安全機構

- **ペーパートレーディングデフォルト**: `config.toml` の `paper = true` が必須。リアル切替は手動のみ
- **ファイルロック**: 同時実行を排他制御で防止
- **冪等性3層**: execution_id + DB重複チェック + client_order_id
- **4段階サーキットブレーカー**: ドローダウン 4% / 7% / 10% / 15% で段階的に取引制限
- **リスク管理**: 1トレード最大リスク1.5%、ポジション上限20%、セクター集中チェック
- **ブラケット注文**: 全エントリーにストップロス（ATR x 2.0）+ テイクプロフィット（5%）を付与

## セットアップ

### 前提条件

- Python 3.11+
- macOS (launchd デプロイの場合)
- [Alpaca](https://alpaca.markets/) アカウント（ペーパートレーディング）
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) インストール済み

### インストール

```bash
git clone https://github.com/your-repo/alpaca-trading.git
cd alpaca-trading
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 環境変数の設定

`.env` ファイルを作成:

```bash
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key
ALPACA_PAPER=true
```

### 動作確認

```bash
# 起動前チェック（全項目パスを確認）
python main.py preflight

# ヘルスチェック
python main.py health_check

# パフォーマンスレポート
python main.py report
```

### launchd デプロイ（自動実行）

```bash
bash deploy/launchd/setup.sh
```

4つのスケジュール（morning / midday / eod / health_check）が launchd に登録される。
DST（夏時間）対応、スリープ復帰対応済み。

## プロジェクト構成

```
alpaca-trading/
├── main.py                    # オーケストレーター（エントリポイント）
├── config.toml                # 全パラメータ設定
├── modules/
│   ├── config.py              # pydantic-settings 設定管理
│   ├── types.py               # 型定義 (dataclasses + Protocol)
│   ├── db.py                  # SQLite WALモード、9テーブル管理
│   ├── logger.py              # JSON Lines ログ (10MB x 5世代ローテーション)
│   ├── universe.py            # S&P500 大型株30銘柄ユニバース
│   ├── data_collector.py      # Alpaca Market Data API → OHLCV + テクニカル指標
│   ├── technical.py           # SMA, RSI, ATR, 出来高比率
│   ├── macro.py               # マクロレジーム判定 (SPY/VIX)
│   ├── llm_analyzer.py        # Claude CLI連携 → 売買判断JSON
│   ├── risk_manager.py        # サーキットブレーカー、ポジションサイジング
│   ├── order_executor.py      # ブラケット注文執行
│   ├── state_manager.py       # Alpaca API ↔ SQLite同期、リコンシリエーション
│   ├── health.py              # 7項目ヘルスチェック
│   ├── backtest.py            # バックテスト (Sharpe/Sortino/max DD)
│   └── stress_test.py         # 5シナリオストレステスト
├── deploy/launchd/            # macOS launchd 設定 (4 plist + setup.sh)
├── prompts/                   # LLM用プロンプトテンプレート
├── docs/                      # 設計ドキュメント
│   ├── strategy.md            # トレーディング戦略
│   ├── system-design.md       # システム設計書
│   ├── phase1-technical-spec.md # 技術仕様書
│   ├── action-plan.md         # アクションプラン
│   └── planning-log.md        # 企画議論ログ
└── tests/                     # テスト (292件, カバレッジ92%)
```

## 戦略概要

- **対象**: S&P500 大型株 30銘柄（セクター分散）
- **手法**: LLMセンチメント（プライマリ）+ テクニカルフィルター（SMA, RSI, 出来高）
- **保有期間**: スイングトレード（2〜10営業日）
- **目標**: シャープレシオ 0.8以上、年率リターン 6-10%（SPY+α）
- **マクロオーバーレイ**: SPY vs 200日MA + VIX でレジーム判定、弱気相場ではエントリー抑制

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| 言語 | Python 3.11+ |
| ブローカー | Alpaca (alpaca-py SDK) |
| データベース | SQLite (WALモード) |
| 設定管理 | pydantic-settings + config.toml |
| LLM | Claude CLI (cron/launchd経由) |
| データソース | Alpaca Market Data, yfinance, FRED API |
| テスト | pytest + ruff + mypy |
| デプロイ | macOS launchd |

## 開発

```bash
# 開発用依存関係のインストール
pip install -r requirements-dev.txt

# テスト実行
pytest

# リンター
ruff check . && ruff format --check .

# 型チェック
mypy --strict modules/types.py

# 時間外テスト（市場クローズ中に実行する場合）
FORCE_MARKET_OPEN=true python main.py morning
```

## ライセンス

Private
