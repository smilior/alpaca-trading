---
name: claude-cli-agent
description: |
  cron + Claude CLIで自律的に動作するAIエージェントを構築するためのスキル。
  以下のキーワードでトリガーする：「Claude CLI」「cron実行」「自動実行」「定期実行」
  「エージェント構築」「自律的」「スケジューラ」「バッチ実行」「Claude Code」
  「非対話実行」「claude -p」「定期タスク」「自動化パイプライン」。
  Claude CLIをcronやスケジューラで定期実行するシステムを構築する際に必ず使用すること。
---

# Claude CLI エージェント構築スキル

## このスキルの目的

cron + Claude CLIで、定期的に自律動作するトレーディングエージェントを構築せよ。人間が寝ている間も市場を監視し、適切なタイミングで売買判断を行うシステムを目指す。

## Claude CLIの基本的な使い方

### 非対話モード（-p フラグ）

```bash
# 基本的な使い方
claude -p "現在のポートフォリオを分析してください"

# ファイルの内容をパイプで渡す
cat portfolio.json | claude -p "このポートフォリオのリスクを分析して"

# モデル指定
claude -p "分析してください" --model claude-sonnet-4-5-20250929

# 出力フォーマット指定
claude -p "JSON形式で回答して" --output-format json

# 最大トークン数指定
claude -p "簡潔に回答して" --max-tokens 1000
```

### 便利なオプション

```bash
# 複数ファイルをコンテキストとして渡す
claude -p "これらのファイルを分析して" \
  --file portfolio.json \
  --file market_data.csv \
  --file strategy_config.yaml

# 実行結果をファイルに保存
claude -p "分析結果をまとめて" > output.md

# エラーをログに記録
claude -p "実行して" 2>> error.log
```

## cron + Claude CLIの基本アーキテクチャ

```
┌─────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────┐
│  cron   │───→│ データ収集    │───→│ Claude   │───→│ 注文実行  │
│ スケジュ │    │ スクリプト   │    │ CLI分析  │    │ スクリプト │
│ ーラー  │    │ (Python)     │    │          │    │ (Python)  │
└─────────┘    └──────────────┘    └──────────┘    └──────────┘
                     │                  │                │
                     ▼                  ▼                ▼
              ┌──────────────┐  ┌──────────────┐  ┌──────────┐
              │ market_data/ │  │ analysis/    │  │ state.db │
              │ (JSON/CSV)   │  │ (判断結果)   │  │ (SQLite) │
              └──────────────┘  └──────────────┘  └──────────┘
```

### 実行フロー

```bash
#!/bin/bash
# trading_agent.sh - メインのエージェントスクリプト

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"
LOG_DIR="$SCRIPT_DIR/logs"
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M:%S)

# ログ設定
LOG_FILE="$LOG_DIR/agent_${DATE}.log"
echo "[$TIME] Agent starting..." >> "$LOG_FILE"

# Step 1: データ収集
python "$SCRIPT_DIR/scripts/collect_data.py" \
  --output "$DATA_DIR/market_${DATE}.json" \
  2>> "$LOG_FILE"

# Step 2: 現在の状態を取得
python "$SCRIPT_DIR/scripts/get_state.py" \
  --output "$DATA_DIR/state_${DATE}.json" \
  2>> "$LOG_FILE"

# Step 3: Claude CLIで分析・判断
ANALYSIS=$(cat "$DATA_DIR/market_${DATE}.json" \
  "$DATA_DIR/state_${DATE}.json" | \
  claude -p "$(cat $SCRIPT_DIR/prompts/trading_decision.md)" \
  --output-format json \
  --max-tokens 2000 \
  2>> "$LOG_FILE")

echo "$ANALYSIS" > "$DATA_DIR/analysis_${DATE}_${TIME}.json"

# Step 4: 判断に基づいて注文実行
python "$SCRIPT_DIR/scripts/execute_orders.py" \
  --analysis "$DATA_DIR/analysis_${DATE}_${TIME}.json" \
  2>> "$LOG_FILE"

echo "[$TIME] Agent completed." >> "$LOG_FILE"
```

## コスト管理

### トークン量の見積もり方法

```
1回の実行あたりのトークン量:
├── プロンプトテンプレート: ~500トークン
├── 市場データ（10銘柄のOHLCV）: ~2,000トークン
├── ポートフォリオ状態: ~500トークン
├── 取引履歴（直近10件）: ~500トークン
├── ニュース要約（5件）: ~1,500トークン
└── 合計入力: ~5,000トークン

出力: ~500-1,000トークン

コスト（Claude Sonnet）:
入力: 5,000 × $3/MTok = $0.015
出力: 1,000 × $15/MTok = $0.015
合計: ~$0.03/実行
```

### コスト削減テクニック

1. **入力データを最小限に**: 全データではなく要約を渡す
2. **Haikuで一次判断**: 「取引判断が必要か」をHaikuで判定し、必要な場合のみSonnetを呼ぶ
3. **キャッシュの活用**: 同じ分析を繰り返さない
4. **実行頻度の最適化**: 市場が動いていない時間帯はスキップ

```
コスト見積もり（月間）:
- 日次1回実行: $0.03 × 22日 = $0.66/月
- 日次3回実行: $0.03 × 66回 = $1.98/月
- 1時間ごと実行: $0.03 × 7h × 22日 = $4.62/月
```

## セキュリティ

### APIキーの管理

```bash
# .env ファイルに保存（gitignore必須）
ALPACA_API_KEY=PKxxxxxxxx
ALPACA_SECRET_KEY=xxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx

# cron実行時に環境変数を読み込む
# crontab内で:
*/30 9-16 * * 1-5 . /path/to/.env && /path/to/trading_agent.sh
```

### 環境変数の安全な受け渡し

```bash
# 方法1: .envファイルをsource
source /path/to/.env

# 方法2: シークレット管理ツール（macOS Keychain等）
ALPACA_API_KEY=$(security find-generic-password -s "alpaca_api_key" -w)

# 方法3: 暗号化されたファイル
# gpg --decrypt secrets.gpg | source /dev/stdin
```

### パーミッション

```bash
# スクリプトとデータの権限を制限
chmod 700 trading_agent.sh
chmod 600 .env
chmod 700 scripts/
```

## 詳細リファレンス

- **cronの設定方法**: [references/cron-patterns.md](references/cron-patterns.md)
- **プロンプト設計**: [references/prompt-design.md](references/prompt-design.md)
- **状態管理**: [references/state-management.md](references/state-management.md)
- **エラー回復**: [references/error-recovery.md](references/error-recovery.md)

## チェックリスト

エージェントを稼働させる前に確認せよ：

- [ ] APIキーがハードコードされていないか
- [ ] .envが.gitignoreに含まれているか
- [ ] ペーパートレーディングモードが明示されているか
- [ ] ログが適切に記録されるか
- [ ] エラー時のフォールバック（何もしない or 全クローズ）が定義されているか
- [ ] コスト見積もりが許容範囲内か
- [ ] cron設定が米国市場時間に合っているか
- [ ] タイムゾーンの設定は正しいか
