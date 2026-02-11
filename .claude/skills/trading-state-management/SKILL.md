---
name: trading-state-management
description: |
  トレーディングボットの状態を安全かつ確実に管理するためのスキル。
  以下のキーワードでトリガーする：「状態管理」「ポートフォリオ管理」「取引履歴」
  「ログ管理」「永続化」「データベース設計」「SQLite」「テーブル設計」
  「ポジション管理」「注文管理」「パフォーマンス記録」「データ保存」。
  トレーディングボットのデータ保存・状態管理に関するコードを書く際に必ず使用すること。
---

# トレーディングボット状態管理スキル

## このスキルの目的

トレーディングボットの状態を安全・確実に管理せよ。状態管理が壊れるとお金を失う。

## なぜ堅牢な状態管理が必要か

状態管理が壊れると以下が発生する：

| 障害 | 結果 | 影響 |
|------|------|------|
| ポジション不整合 | 既にクローズ済みのポジションに追加注文 | 意図しないポジション |
| 二重注文 | 同じシグナルで2回注文を送信 | ポジション過大 |
| 残高計算ミス | 購買力の誤計算 | リスク制限の無意味化 |
| 取引履歴の欠損 | パフォーマンス評価が不正確 | 改善不能 |

## 管理すべき状態の一覧

| 状態 | 説明 | 更新タイミング |
|------|------|---------------|
| 現在のポジション | 保有銘柄、数量、エントリー価格 | 注文約定時 |
| 未約定注文 | 送信済みだが未約定の注文 | 注文送信/約定/キャンセル時 |
| 取引履歴 | 過去の全取引記録 | 注文約定時 |
| 残高推移 | 日次の口座残高 | 日次クローズ時 |
| 戦略パラメータ | 現在の戦略設定 | パラメータ変更時 |
| 実行ログ | エージェントの全実行記録 | 毎実行時 |

## Alpaca APIとローカル状態の同期

### 方針: Alpacaを信頼のソース（Source of Truth）にする

```
推奨アプローチ:

Alpaca API（信頼のソース）
├── ポジション → client.get_all_positions()
├── 注文 → client.get_orders()
└── 口座残高 → client.get_account()

ローカルDB（補助データ）
├── 取引の理由・戦略メモ（Alpacaにはない）
├── パフォーマンス指標の計算済みデータ
├── エージェントの判断ログ
└── 戦略パラメータの履歴
```

**なぜAlpacaを信頼のソースにするか**:
- Alpacaが実際の約定・ポジションを管理している
- ローカルDBとAlpacaがずれた場合、Alpacaが正しい
- ローカルDBはあくまで「追加情報」の保存用

```python
def sync_with_alpaca(client, local_db):
    """AlpacaのポジションとローカルDBを同期"""
    # Alpacaからポジション取得
    alpaca_positions = client.get_all_positions()
    alpaca_symbols = {p.symbol for p in alpaca_positions}

    # ローカルDBのポジション取得
    local_positions = local_db.get_open_positions()
    local_symbols = {p['symbol'] for p in local_positions}

    # 不整合チェック
    only_alpaca = alpaca_symbols - local_symbols
    only_local = local_symbols - alpaca_symbols

    if only_alpaca:
        logger.warning(f"Alpacaにあるがローカルにない: {only_alpaca}")
        # Alpacaから取得してローカルに追加
        for pos in alpaca_positions:
            if pos.symbol in only_alpaca:
                local_db.upsert_position(pos)

    if only_local:
        logger.warning(f"ローカルにあるがAlpacaにない: {only_local}")
        # ローカルのポジションをクローズ済みに更新
        for symbol in only_local:
            local_db.close_position(symbol, reason="sync_mismatch")
```

## SQLiteを推奨する理由

1. **ファイルベース**: サーバー不要。`trading.db` ファイル1つで完結
2. **軽量**: メモリ使用量が少ない。ボットには十分な性能
3. **トランザクション**: ACID特性。データの整合性を保証
4. **バックアップが簡単**: ファイルをコピーするだけ
5. **Pythonに標準搭載**: 追加インストール不要
6. **WALモード**: 読み書きの並行処理が可能

### テーブル設計

詳細は [references/schema-design.md](references/schema-design.md) を参照。

## 初期化スクリプト

[scripts/init-state-db.py](scripts/init-state-db.py) を実行してデータベースを初期化せよ。

```bash
python scripts/init-state-db.py --db-path data/state/trading.db
```

## 状態管理のベストプラクティス

### 1. 全操作をトランザクションで行う

```python
def record_trade_and_update_position(db, trade, position_update):
    """取引記録とポジション更新をアトミックに実行"""
    with db.conn:  # トランザクション
        db.conn.execute("INSERT INTO trades (...) VALUES (...)", trade)
        db.conn.execute("UPDATE positions SET ... WHERE ...", position_update)
    # コミットはwithブロック終了時に自動実行
```

### 2. 毎回の実行開始時にAlpacaと同期

```python
def agent_main():
    # 最初にAlpacaとの同期
    sync_with_alpaca(alpaca_client, local_db)

    # 次にリスクチェック
    risk_check(local_db)

    # その後に分析・判断
    ...
```

### 3. 全操作をログに記録

```python
def execute_order(client, db, order_request):
    """注文実行（ログ記録付き）"""
    db.log_execution("order_submit", {
        "symbol": order_request.symbol,
        "side": str(order_request.side),
        "qty": order_request.qty
    })

    order = client.submit_order(order_request)

    db.log_execution("order_submitted", {
        "order_id": str(order.id),
        "status": str(order.status)
    })

    return order
```

## アンチパターン

```
❌ 悪い例: 状態をグローバル変数で管理
→ プロセス終了で状態が消える

❌ 悪い例: JSONファイルに全状態を書き込む
→ 書き込み中にクラッシュするとファイルが壊れる

❌ 悪い例: ローカルDBだけを信頼する
→ Alpacaとの不整合に気づかない

✅ 良い例: SQLiteで管理し、毎回Alpacaと同期
→ データの整合性が保証され、APIとのずれも検出できる
```
