# SQLite テーブル設計 リファレンス

## テーブル一覧

| テーブル名 | 用途 | 主要なクエリ |
|-----------|------|-------------|
| positions | 現在のポジション管理 | 「AAPL持ってる？」「全ポジションは？」 |
| orders | 注文の記録 | 「未約定の注文は？」「今日の注文は？」 |
| trades | 約定済み取引の記録 | 「過去30日の取引は？」 |
| daily_performance | 日次パフォーマンス | 「先月の日次リターンは？」 |
| strategy_params | 戦略パラメータ履歴 | 「パラメータをいつ変えた？」 |
| execution_logs | エージェント実行ログ | 「最後の実行は？」「エラーは？」 |

## テーブル定義

### positions（ポジション）

```sql
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    qty REAL NOT NULL,
    avg_entry_price REAL NOT NULL,
    current_price REAL,
    unrealized_pnl REAL,
    stop_loss_price REAL,
    take_profit_price REAL,
    strategy TEXT,
    entry_date TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed')),
    close_date TEXT,
    close_price REAL,
    realized_pnl REAL,
    close_reason TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_entry_date ON positions(entry_date);
```

### orders（注文）

```sql
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alpaca_order_id TEXT UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    order_type TEXT NOT NULL CHECK(order_type IN
        ('market', 'limit', 'stop', 'stop_limit', 'trailing_stop')),
    limit_price REAL,
    stop_price REAL,
    trail_percent REAL,
    time_in_force TEXT NOT NULL DEFAULT 'day',
    status TEXT NOT NULL DEFAULT 'new',
    filled_qty REAL DEFAULT 0,
    filled_avg_price REAL,
    submitted_at TEXT NOT NULL,
    filled_at TEXT,
    canceled_at TEXT,
    expired_at TEXT,
    strategy TEXT,
    signal_score REAL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_submitted_at ON orders(submitted_at);
CREATE INDEX IF NOT EXISTS idx_orders_alpaca_id ON orders(alpaca_order_id);
```

### trades（約定済み取引）

```sql
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    price REAL NOT NULL,
    total_value REAL NOT NULL,
    commission REAL DEFAULT 0,
    slippage REAL DEFAULT 0,
    pnl REAL,
    pnl_pct REAL,
    holding_period_days INTEGER,
    strategy TEXT,
    entry_reason TEXT,
    exit_reason TEXT,
    timestamp TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
```

### daily_performance（日次パフォーマンス）

```sql
CREATE TABLE IF NOT EXISTS daily_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    portfolio_value REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    daily_pnl REAL NOT NULL,
    daily_return_pct REAL NOT NULL,
    cumulative_return_pct REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    max_drawdown_pct REAL NOT NULL,
    trade_count INTEGER DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    sharpe_ratio_30d REAL,
    benchmark_return_pct REAL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_perf_date ON daily_performance(date);
```

### strategy_params（戦略パラメータ履歴）

```sql
CREATE TABLE IF NOT EXISTS strategy_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    params_json TEXT NOT NULL,
    version TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    change_reason TEXT,
    performance_before TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_strategy_params_name ON strategy_params(strategy_name);
CREATE INDEX IF NOT EXISTS idx_strategy_params_effective ON strategy_params(effective_from);
```

### execution_logs（実行ログ）

```sql
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    details_json TEXT,
    level TEXT NOT NULL DEFAULT 'info'
        CHECK(level IN ('debug', 'info', 'warning', 'error', 'critical')),
    agent_version TEXT,
    execution_time_ms INTEGER,
    tokens_used INTEGER,
    cost_usd REAL
);

CREATE INDEX IF NOT EXISTS idx_exec_logs_timestamp ON execution_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_exec_logs_level ON execution_logs(level);
CREATE INDEX IF NOT EXISTS idx_exec_logs_event ON execution_logs(event_type);
```

## よく使うクエリ

### 直近30日のパフォーマンスサマリー

```sql
SELECT
    COUNT(*) as trading_days,
    SUM(daily_pnl) as total_pnl,
    AVG(daily_return_pct) as avg_daily_return,
    MIN(daily_return_pct) as worst_day,
    MAX(daily_return_pct) as best_day,
    MIN(drawdown_pct) as max_drawdown,
    SUM(win_count) as total_wins,
    SUM(loss_count) as total_losses
FROM daily_performance
WHERE date >= date('now', '-30 days');
```

### 戦略別の勝率

```sql
SELECT
    strategy,
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
    ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
    ROUND(AVG(pnl), 2) as avg_pnl,
    ROUND(SUM(pnl), 2) as total_pnl
FROM trades
GROUP BY strategy;
```

### 現在のポートフォリオ状態

```sql
SELECT
    p.symbol,
    p.side,
    p.qty,
    p.avg_entry_price,
    p.current_price,
    p.unrealized_pnl,
    p.stop_loss_price,
    p.entry_date,
    julianday('now') - julianday(p.entry_date) as holding_days
FROM positions p
WHERE p.status = 'open'
ORDER BY p.unrealized_pnl DESC;
```

## マイグレーション方針

スキーマを変更する場合は、以下の手順を踏め：

1. マイグレーションスクリプトを作成（`migrate_v1_to_v2.py`等）
2. バックアップを取る
3. マイグレーションを実行
4. データの整合性を確認

```python
def migrate_v1_to_v2(db_path):
    """v1 → v2 マイグレーション"""
    import shutil
    from datetime import datetime

    # バックアップ
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)

    conn = sqlite3.connect(db_path)
    try:
        # カラム追加の例
        conn.execute("ALTER TABLE positions ADD COLUMN sector TEXT")
        conn.execute("ALTER TABLE trades ADD COLUMN market_regime TEXT")
        conn.commit()
        print("マイグレーション完了")
    except Exception as e:
        print(f"マイグレーション失敗: {e}")
        print(f"バックアップから復元: {backup_path}")
        shutil.copy2(backup_path, db_path)
    finally:
        conn.close()
```
