# レポートテンプレート リファレンス

## 日次レポート

毎営業日のクローズ後に生成する。主な目的はリスク確認と異常検出。

```markdown
# 日次トレーディングレポート: {date}

## サマリー
| 指標 | 値 |
|------|------|
| ポートフォリオ価値 | ${portfolio_value:,.2f} |
| 前日比 | ${daily_pnl:+,.2f} ({daily_return:+.2f}%) |
| ベンチマーク(SPY) | {spy_return:+.2f}% |
| 超過リターン(α) | {alpha:+.2f}% |
| 現在のドローダウン | {drawdown:.2f}% |

## ポジション
| 銘柄 | サイド | 数量 | 平均取得 | 現在値 | 含み損益 | ストップ |
|------|--------|------|----------|--------|----------|---------|
| {symbol} | {side} | {qty} | ${entry} | ${current} | ${pnl} | ${stop} |

## 本日の取引
| 時刻 | 銘柄 | サイド | 数量 | 価格 | 損益 | 理由 |
|------|------|--------|------|------|------|------|
| {time} | {symbol} | {side} | {qty} | ${price} | ${pnl} | {reason} |

## リスク状況
| リスク指標 | 現在値 | 上限 | ステータス |
|-----------|--------|------|----------|
| 日次損失 | {daily_loss}% | 5% | {status} |
| ドローダウン | {dd}% | 15% | {status} |
| ポジション数 | {pos_count} | {max_pos} | {status} |
| 最大セクター集中 | {sector_conc}% | 40% | {status} |

## 注意事項
- {notable_events}
```

## 週次レポート

毎週金曜のクローズ後に生成。短期トレンドの把握と戦略の微調整用。

```markdown
# 週次トレーディングレポート: {week_start} ~ {week_end}

## 週次サマリー
| 指標 | 今週 | 先週 | 変化 |
|------|------|------|------|
| ポートフォリオ価値 | ${value} | ${prev_value} | {change}% |
| 週次リターン | {return}% | {prev_return}% | - |
| SPY週次リターン | {spy}% | {prev_spy}% | - |
| 超過リターン(α) | {alpha}% | - | - |
| 取引回数 | {trades} | {prev_trades} | - |
| 勝率 | {win_rate}% | {prev_win_rate}% | - |

## 取引パフォーマンス
| 指標 | 値 |
|------|------|
| 総取引回数 | {total_trades} |
| 勝ちトレード | {wins} |
| 負けトレード | {losses} |
| 勝率 | {win_rate}% |
| 平均利益 | ${avg_win} |
| 平均損失 | ${avg_loss} |
| ペイオフレシオ | {payoff_ratio} |
| プロフィットファクター | {profit_factor} |
| 期待値/トレード | ${expectancy} |

## ベスト/ワースト取引
| ランク | 銘柄 | 損益 | 保有期間 | 理由 |
|--------|------|------|----------|------|
| Best 1 | {symbol} | +${pnl} | {days}日 | {reason} |
| Best 2 | ... | ... | ... | ... |
| Worst 1 | {symbol} | -${pnl} | {days}日 | {reason} |
| Worst 2 | ... | ... | ... | ... |

## セクター別パフォーマンス
| セクター | 取引数 | 損益合計 | 勝率 |
|----------|--------|----------|------|
| {sector} | {count} | ${pnl} | {win_rate}% |

## 今週の学び
- {lesson_1}
- {lesson_2}

## 来週の注目ポイント
- {events: 決算発表、FOMC等}
- {adjustments: 戦略の微調整があれば}
```

## 月次レポート

月末に生成する。戦略の有効性の総合評価と改善計画の策定用。

```markdown
# 月次トレーディングレポート: {year}年{month}月

## エグゼクティブサマリー
{1-2文の総括}

## パフォーマンス概要
| 指標 | 当月 | 前月 | 年初来 |
|------|------|------|--------|
| リターン | {return}% | {prev}% | {ytd}% |
| SPYリターン | {spy}% | {spy_prev}% | {spy_ytd}% |
| 超過リターン(α) | {alpha}% | - | {alpha_ytd}% |
| シャープレシオ(月間) | {sharpe} | {prev_sharpe} | {ytd_sharpe} |
| 最大ドローダウン | {mdd}% | - | {ytd_mdd}% |

## 詳細KPI
| KPI | 値 | 基準 | 判定 |
|-----|------|------|------|
| シャープレシオ | {sharpe} | > 1.0 | {pass/fail} |
| ソルティノレシオ | {sortino} | > 1.5 | {pass/fail} |
| プロフィットファクター | {pf} | > 1.5 | {pass/fail} |
| 最大ドローダウン | {mdd}% | < 15% | {pass/fail} |
| 勝率 | {wr}% | - | - |
| ペイオフレシオ | {pr} | > 1.5 | {pass/fail} |
| 期待値/トレード | ${exp} | > 0 | {pass/fail} |
| 総取引回数 | {trades} | > 20 | {pass/fail} |

## 日次リターン分布
```
{テキストベースのヒストグラム}
 -3% |
 -2% | ██
 -1% | ████████
  0% | ██████████████
 +1% | ██████████
 +2% | ████
 +3% | █
```

## 月次リターン推移（年初来）
```
{テキストベースのバーチャート}
1月: ████████████  +3.2%
2月: █████████     +2.5%
3月: ██████████████ +4.1%
...
```

## 戦略別パフォーマンス
| 戦略 | 取引数 | 勝率 | PF | シャープ | 総損益 |
|------|--------|------|-----|---------|--------|
| {strategy_name} | {count} | {wr}% | {pf} | {sharpe} | ${pnl} |

## リスク分析
- 最大日次損失: {worst_day}% ({date})
- 最大連続損失日数: {consecutive_losses}日
- 現在のドローダウン: {current_dd}%
- ドローダウン回復日数（平均）: {avg_recovery}日

## 改善計画
### うまくいったこと
- {positive_1}

### 改善が必要なこと
- {improvement_1}

### 来月のアクション
1. {action_1}
2. {action_2}

## リアルマネー移行チェック（ペーパートレーディング中のみ）
| 基準 | 目標 | 現在 | 達成 |
|------|------|------|------|
| 運用期間 | 3ヶ月以上 | {months}ヶ月 | {pass/fail} |
| 取引回数 | 100回以上 | {trades} | {pass/fail} |
| シャープレシオ | > 1.0 | {sharpe} | {pass/fail} |
| 最大ドローダウン | < 15% | {mdd}% | {pass/fail} |
| プロフィットファクター | > 1.5 | {pf} | {pass/fail} |
| ベンチマーク超過 | SPY上回り | {alpha}% | {pass/fail} |
```

## テキストベースの可視化

### ヒストグラム生成

```python
def text_histogram(values, bins=10, width=40):
    """テキストベースのヒストグラム"""
    counts, edges = np.histogram(values, bins=bins)
    max_count = max(counts)

    lines = []
    for i in range(len(counts)):
        bar_len = int(counts[i] / max_count * width) if max_count > 0 else 0
        bar = "█" * bar_len
        label = f"{edges[i]:+.1f}%"
        lines.append(f"{label:>7s} | {bar} ({counts[i]})")

    return "\n".join(lines)
```

### リターン推移チャート

```python
def text_bar_chart(labels, values, width=30):
    """テキストベースのバーチャート"""
    max_abs = max(abs(v) for v in values) if values else 1

    lines = []
    for label, value in zip(labels, values):
        bar_len = int(abs(value) / max_abs * width)
        if value >= 0:
            bar = "█" * bar_len
            lines.append(f"{label}: {bar} +{value:.1f}%")
        else:
            bar = "█" * bar_len
            lines.append(f"{label}: {' ' * (width - bar_len)}{bar} {value:.1f}%")

    return "\n".join(lines)
```
