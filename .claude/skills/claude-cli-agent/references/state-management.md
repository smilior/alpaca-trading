# 状態管理 リファレンス

## 実行間の状態永続化

Claude CLIは各実行が独立しているため、実行間で状態を引き継ぐには外部に永続化する必要がある。

## 永続化方式の比較

| 方式 | メリット | デメリット | 推奨用途 |
|------|----------|-----------|----------|
| JSONファイル | シンプル、可読性高い | 並行書き込み不安全、クエリ不可 | 設定・パラメータ |
| SQLite | クエリ可能、トランザクション | やや複雑 | 取引履歴・パフォーマンス |
| CSV | Excel等で開ける | 型情報なし、追記のみ | ログ・レポート |

### 推奨構成

```
data/
├── config/
│   ├── strategy_params.json   # 戦略パラメータ（JSON）
│   └── risk_limits.json       # リスク制限値（JSON）
├── state/
│   └── trading.db             # メインの状態DB（SQLite）
├── logs/
│   ├── agent_2024-01-15.log   # 日次ログ
│   └── trades_2024-01.csv     # 月次取引ログ（CSV）
└── cache/
    └── market_data_cache.json # 一時キャッシュ
```

## JSONファイルでの管理

### 戦略パラメータ

```json
{
  "strategy_name": "momentum_sentiment",
  "version": "1.2",
  "last_updated": "2024-01-15T16:30:00",
  "parameters": {
    "fast_ma_period": 10,
    "slow_ma_period": 50,
    "rsi_period": 14,
    "rsi_buy_threshold": 35,
    "rsi_sell_threshold": 65,
    "sentiment_weight": 0.3,
    "atr_stop_multiplier": 2.0
  },
  "universe": ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA"],
  "risk_limits": {
    "max_position_risk_pct": 0.02,
    "max_daily_loss_pct": 0.05,
    "max_positions": 5,
    "max_drawdown_pct": 0.15
  }
}
```

```python
import json
from pathlib import Path

class ConfigManager:
    """設定ファイルの管理"""

    def __init__(self, config_dir="data/config"):
        self.config_dir = Path(config_dir)

    def load(self, filename):
        path = self.config_dir / filename
        with open(path) as f:
            return json.load(f)

    def save(self, filename, data):
        path = self.config_dir / filename
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
```

## SQLiteでの管理

### なぜSQLiteか

- **ファイルベース**: サーバー不要、バックアップはファイルコピーだけ
- **トランザクション**: データの整合性が保証される
- **クエリ可能**: 「直近30日の勝率」等を簡単に計算できる
- **並行書き込み**: WALモードで読み書きが同時に可能

### テーブル設計

詳細は `trading-state-management` スキルの [references/schema-design.md](../../trading-state-management/references/schema-design.md) を参照。

### 基本的な使い方

```python
import sqlite3
from datetime import datetime

class StateDB:
    """状態管理データベース"""

    def __init__(self, db_path="data/state/trading.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row

    def get_current_positions(self):
        """現在のポジションを取得"""
        cursor = self.conn.execute("""
            SELECT * FROM positions WHERE status = 'open'
        """)
        return [dict(row) for row in cursor.fetchall()]

    def record_trade(self, trade_data):
        """取引を記録"""
        self.conn.execute("""
            INSERT INTO trades
            (symbol, side, qty, price, timestamp, strategy, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data['symbol'],
            trade_data['side'],
            trade_data['qty'],
            trade_data['price'],
            datetime.now().isoformat(),
            trade_data.get('strategy', ''),
            trade_data.get('notes', '')
        ))
        self.conn.commit()

    def get_daily_pnl(self, date=None):
        """日次損益を取得"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        cursor = self.conn.execute("""
            SELECT SUM(pnl) as total_pnl,
                   COUNT(*) as trade_count,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses
            FROM trades
            WHERE DATE(timestamp) = ?
        """, (date,))
        return dict(cursor.fetchone())
```

## Claude CLIへの状態の渡し方

```python
def prepare_context_for_claude(state_db, config_mgr):
    """Claude CLIに渡すコンテキストを準備"""
    context = {
        "positions": state_db.get_current_positions(),
        "recent_trades": state_db.get_recent_trades(limit=10),
        "daily_pnl": state_db.get_daily_pnl(),
        "strategy_params": config_mgr.load("strategy_params.json"),
        "risk_status": {
            "current_drawdown": state_db.get_current_drawdown(),
            "daily_loss": state_db.get_daily_pnl().get('total_pnl', 0),
            "open_positions_count": len(state_db.get_current_positions())
        }
    }
    return json.dumps(context, indent=2, default=str)
```

## バックアップ

```bash
# 日次バックアップ（cron）
0 17 * * 1-5 cp /path/to/data/state/trading.db \
  /path/to/backups/trading_$(date +\%Y-\%m-\%d).db

# 古いバックアップの削除（30日以上前）
0 18 * * 0 find /path/to/backups -name "trading_*.db" -mtime +30 -delete
```
