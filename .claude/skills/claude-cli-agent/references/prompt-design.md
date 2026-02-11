# プロンプト設計 リファレンス

## プロンプト設計の原則

Claude CLIに渡すプロンプトは、トレーディングの判断品質に直結する。以下の原則を守れ。

### 原則1: コンテキストを必要十分に渡す

```
❌ 悪い例:
「AAPLを買うべきか？」
→ 市場環境、ポートフォリオ状態、戦略パラメータが一切不明

✅ 良い例:
「以下のコンテキストに基づいてAAPLの売買判断を行え」
+ 現在のポートフォリオ状態
+ 直近の市場データ
+ 戦略パラメータ
+ 取引履歴
```

### 原則2: 出力形式を厳密に指定する

```
❌ 悪い例:
「分析結果を教えて」
→ 自由形式のテキストが返り、パースできない

✅ 良い例:
「以下のJSON形式で回答せよ。JSON以外の文字は出力するな。」
+ 具体的なスキーマを提示
```

### 原則3: 判断の根拠を出力させる

```
✅ 良い例:
「判断と共に、以下を出力せよ:
1. 判断（BUY/SELL/HOLD）
2. 確信度（0-100）
3. 判断の根拠（3つ以上）
4. リスク要因
5. 判断を変更すべき条件」
```

## プロンプトテンプレート

### テンプレート1: 日次トレーディング判断

```markdown
# トレーディング判断プロンプト

あなたはクオンツトレーディングエージェントである。
以下のデータに基づいて売買判断を行え。

## 制約条件
- ペーパートレーディングモード
- 1トレードの最大リスク: 総資金の2%
- 最大同時ポジション数: 5
- 日次最大損失: 総資金の5%

## 現在のポートフォリオ
```json
{portfolio_json}
```

## 市場データ（直近5日間）
```json
{market_data_json}
```

## 直近の取引履歴（最新10件）
```json
{trade_history_json}
```

## ニュース要約
{news_summary}

## 戦略パラメータ
```json
{strategy_params_json}
```

## 指示
上記データに基づいて、以下のJSON形式で判断を出力せよ。
JSON以外のテキストは出力するな。

```json
{
  "timestamp": "YYYY-MM-DDTHH:MM:SS",
  "decisions": [
    {
      "symbol": "AAPL",
      "action": "BUY|SELL|HOLD",
      "quantity": 0,
      "order_type": "market|limit",
      "limit_price": null,
      "stop_loss": 0.0,
      "take_profit": null,
      "confidence": 0-100,
      "reasoning": ["理由1", "理由2", "理由3"],
      "risk_factors": ["リスク1", "リスク2"]
    }
  ],
  "portfolio_assessment": {
    "overall_risk": "low|medium|high",
    "suggested_adjustments": ["調整1"],
    "market_regime": "bull|bear|range"
  },
  "meta": {
    "data_quality": "good|degraded|poor",
    "data_concerns": []
  }
}
```
```

### テンプレート2: ニュースセンチメント分析

```markdown
# ニュースセンチメント分析プロンプト

以下のニュース記事を分析し、対象銘柄への影響を評価せよ。

## ニュース
{news_articles}

## 指示
各ニュースについて以下のJSON形式で分析結果を出力せよ。

```json
{
  "analyses": [
    {
      "headline": "記事のヘッドライン",
      "symbols_affected": ["AAPL"],
      "sentiment": -1.0 to 1.0,
      "impact_timeframe": "immediate|short_term|long_term",
      "confidence": 0-100,
      "key_points": ["ポイント1"],
      "contrarian_view": "逆の解釈がある場合"
    }
  ],
  "overall_market_sentiment": -1.0 to 1.0,
  "key_themes": ["テーマ1"]
}
```
```

### テンプレート3: 日次パフォーマンスレビュー

```markdown
# 日次パフォーマンスレビュープロンプト

本日のトレーディング結果をレビューし、改善点を特定せよ。

## 本日の取引
```json
{today_trades_json}
```

## 本日の損益
```json
{today_pnl_json}
```

## ポートフォリオ状態（クローズ時点）
```json
{portfolio_close_json}
```

## 指示
以下の形式でレビュー結果を出力せよ。

```json
{
  "date": "YYYY-MM-DD",
  "summary": {
    "total_pnl": 0.0,
    "win_count": 0,
    "loss_count": 0,
    "best_trade": {"symbol": "", "pnl": 0},
    "worst_trade": {"symbol": "", "pnl": 0}
  },
  "lessons": [
    {
      "observation": "何が起きたか",
      "lesson": "何を学んだか",
      "action": "次にどうするか"
    }
  ],
  "strategy_adjustments": [
    {
      "parameter": "調整するパラメータ",
      "current_value": "",
      "suggested_value": "",
      "reasoning": "変更理由"
    }
  ],
  "risk_alerts": ["アラートがあれば"]
}
```
```

## データの渡し方のベストプラクティス

### 方法1: パイプで渡す

```bash
# データ収集→JSON化→Claude CLIにパイプ
python collect_data.py | claude -p "$(cat prompt_template.md)"
```

### 方法2: テンプレートの変数展開

```bash
# envsubst を使ってテンプレートの変数を展開
export PORTFOLIO_JSON=$(python get_portfolio.py)
export MARKET_DATA=$(python get_market_data.py)
envsubst < prompt_template.md | claude -p "$(cat /dev/stdin)"
```

### 方法3: Pythonからの実行

```python
import subprocess
import json

def run_claude_analysis(prompt, data):
    """Claude CLIを実行して分析結果を取得"""
    full_prompt = prompt.format(**data)

    result = subprocess.run(
        ['claude', '-p', full_prompt, '--output-format', 'json'],
        capture_output=True,
        text=True,
        timeout=120  # 2分タイムアウト
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr}")

    return json.loads(result.stdout)
```

## トークン節約のテクニック

### データの圧縮

```python
def compress_market_data(bars_df, symbols):
    """市場データを最小限のJSON形式に圧縮"""
    compressed = {}
    for symbol in symbols:
        data = bars_df.loc[symbol].tail(5)  # 直近5日のみ
        compressed[symbol] = {
            'close': data['close'].tolist(),
            'volume': data['volume'].tolist(),
            'change_pct': data['close'].pct_change().dropna().tolist()
        }
    return json.dumps(compressed)

# フルデータ: ~5,000トークン → 圧縮後: ~500トークン
```

### 段階的分析（2段階方式）

```bash
# Stage 1: Haikuで一次スクリーニング（低コスト）
SCREEN=$(claude -p "以下の10銘柄から、取引判断が必要な銘柄だけをリストアップせよ" \
  --model claude-haiku-4-5-20251001)

# Stage 2: Sonnetで詳細分析（高精度、対象銘柄のみ）
ANALYSIS=$(echo "$SCREEN" | claude -p "これらの銘柄について詳細な売買判断を行え" \
  --model claude-sonnet-4-5-20250929)
```
