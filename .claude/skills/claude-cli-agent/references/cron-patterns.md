# cron パターン リファレンス

## crontabの基本

```
* * * * *
│ │ │ │ │
│ │ │ │ └── 曜日（0-7, 0=日, 7=日）
│ │ │ └──── 月（1-12）
│ │ └────── 日（1-31）
│ └──────── 時（0-23）
└────────── 分（0-59）
```

## 米国市場の取引時間

```
市場時間（米国東部時間 EST/EDT）:
- プレマーケット: 4:00 AM - 9:30 AM ET
- レギュラー: 9:30 AM - 4:00 PM ET
- アフターマーケット: 4:00 PM - 8:00 PM ET

日本時間（JST）への換算:
- EST（冬時間, 11月-3月）: +14時間
  → レギュラー: 23:30 - 6:00 JST（翌日）
- EDT（夏時間, 3月-11月）: +13時間
  → レギュラー: 22:30 - 5:00 JST（翌日）
```

**重要**: crontabのタイムゾーンはサーバーのローカルタイムゾーンに依存する。

```bash
# macOSの場合、タイムゾーンを確認
date +%Z

# crontabでタイムゾーンを明示する方法
# (一部のcron実装でサポート)
CRON_TZ=America/New_York
```

## トレーディング用cronパターン

### パターン1: 市場オープン直前（9:25 AM ET）

```bash
# EST（サーバーがEST）
25 9 * * 1-5 /path/to/pre_market_analysis.sh

# JST（サーバーがJST、冬時間）
25 23 * * 1-5 /path/to/pre_market_analysis.sh

# JST（サーバーがJST、夏時間）
25 22 * * 0-4 /path/to/pre_market_analysis.sh
# 注: 曜日がずれる（月曜の22:25 JSTは月曜の9:25 AM EDT）
```

### パターン2: 取引時間中30分ごと

```bash
# EST
*/30 9-15 * * 1-5 /path/to/trading_agent.sh
# 9:00, 9:30, 10:00, ..., 15:30

# 注: 9:30開始に合わせたい場合
0,30 10-15 * * 1-5 /path/to/trading_agent.sh
30 9 * * 1-5 /path/to/trading_agent.sh
```

### パターン3: 市場クローズ後（4:15 PM ET）

```bash
# EST
15 16 * * 1-5 /path/to/daily_summary.sh
```

### パターン4: 週次レビュー（金曜クローズ後）

```bash
# EST 金曜4:30 PM
30 16 * * 5 /path/to/weekly_review.sh
```

### 推奨スケジュール（完全版）

```bash
# crontab -e

# タイムゾーン設定（サーバーがESTの場合不要）
# CRON_TZ=America/New_York

# 環境変数の読み込みパス
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# === 市場日のみ実行 ===
# （祝日チェックは別途スクリプト内で行う）

# 1. プレマーケット分析（9:15 AM ET）
15 9 * * 1-5 . ~/.trading_env && /path/to/scripts/pre_market.sh

# 2. 市場オープン直後（9:35 AM ET）
35 9 * * 1-5 . ~/.trading_env && /path/to/scripts/opening_check.sh

# 3. 取引時間中（1時間ごと、10:00-15:00 ET）
0 10-15 * * 1-5 . ~/.trading_env && /path/to/scripts/trading_agent.sh

# 4. 市場クローズ前（3:45 PM ET）
45 15 * * 1-5 . ~/.trading_env && /path/to/scripts/closing_check.sh

# 5. 日次サマリー（4:30 PM ET）
30 16 * * 1-5 . ~/.trading_env && /path/to/scripts/daily_summary.sh

# 6. 週次レビュー（金曜 5:00 PM ET）
0 17 * * 5 . ~/.trading_env && /path/to/scripts/weekly_review.sh
```

## 祝日カレンダーの扱い

米国市場は以下の祝日に休場する。cron自体は実行されるため、スクリプト内で祝日チェックを行う必要がある。

### 主要な米国市場休場日

- New Year's Day（1月1日）
- Martin Luther King Jr. Day（1月第3月曜）
- Presidents' Day（2月第3月曜）
- Good Friday（復活祭の金曜日、毎年異なる）
- Memorial Day（5月最終月曜）
- Juneteenth（6月19日）
- Independence Day（7月4日）
- Labor Day（9月第1月曜）
- Thanksgiving（11月第4木曜）
- Christmas Day（12月25日）

### 祝日チェックの実装

```python
from datetime import date, datetime

# Alpaca APIで市場カレンダーを取得する方法（推奨）
from alpaca.trading.client import TradingClient

def is_trading_day(client, check_date=None):
    """指定日が取引日か確認"""
    if check_date is None:
        check_date = date.today()

    calendar = client.get_calendar(
        start=check_date.isoformat(),
        end=check_date.isoformat()
    )

    if not calendar:
        return False

    cal_date = calendar[0].date
    return cal_date == check_date
```

```bash
# trading_agent.sh の冒頭に追加
if ! python /path/to/scripts/check_trading_day.py; then
    echo "$(date): Not a trading day. Skipping." >> "$LOG_FILE"
    exit 0
fi
```

## 半日営業日

一部の祝日前日は13:00 ET（1:00 PM）に早期クローズ。

```
- Independence Day前日（7月3日）
- Thanksgiving翌日（ブラックフライデー）
- Christmas前日（12月24日）
```

スクリプト内で `client.get_calendar()` の `close` 時間を確認して対応。

## cron実行のデバッグ

```bash
# cronのログを確認（macOS）
log show --predicate 'process == "cron"' --last 1h

# cronのメール通知を設定
MAILTO="your-email@example.com"

# cronの環境変数をデバッグ
* * * * * env > /tmp/cron_env.txt  # 1回だけ実行して削除

# 手動で同じ環境でテスト
env -i HOME=$HOME SHELL=/bin/bash PATH=/usr/local/bin:/usr/bin:/bin \
  /path/to/trading_agent.sh
```
