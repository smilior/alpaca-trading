# セクター分析 リファレンス

## GICS 11セクターの概要

GICS（Global Industry Classification Standard）はMSCIとS&Pが策定した産業分類。

### 各セクターの特徴

| # | セクター | 代表ETF | 代表銘柄 | 特徴 |
|---|----------|---------|----------|------|
| 1 | Information Technology | XLK | AAPL, MSFT, NVDA | 成長株。金利に敏感 |
| 2 | Health Care | XLV | JNJ, UNH, PFE | ディフェンシブ。規制リスク |
| 3 | Financials | XLF | JPM, BAC, BRK.B | 金利上昇で恩恵 |
| 4 | Consumer Discretionary | XLY | AMZN, TSLA, HD | 景気敏感。消費者信頼感に連動 |
| 5 | Communication Services | XLC | GOOG, META, NFLX | 広告収入依存。成長/バリュー混在 |
| 6 | Industrials | XLI | CAT, HON, UPS | 景気敏感。インフラ投資に連動 |
| 7 | Consumer Staples | XLP | PG, KO, WMT | ディフェンシブ。低ボラティリティ |
| 8 | Energy | XLE | XOM, CVX, COP | 原油価格に強く連動 |
| 9 | Utilities | XLU | NEE, DUK, SO | 高配当。金利上昇に弱い |
| 10 | Real Estate | XLRE | AMT, PLD, CCI | 金利に敏感。REIT中心 |
| 11 | Materials | XLB | LIN, APD, SHW | コモディティ価格に連動 |

## セクターローテーション理論

景気サイクルに応じて、強いセクターが入れ替わる（Sam Stovallの理論）。

### 景気サイクルとセクター

```
景気回復期（Early Recovery）
├── 強い: Financials, Consumer Discretionary, Industrials
└── 弱い: Utilities, Consumer Staples

景気拡大期（Mid Expansion）
├── 強い: Technology, Communication Services
└── 弱い: Utilities, Energy

景気後期（Late Expansion）
├── 強い: Energy, Materials, Industrials
└── 弱い: Technology, Consumer Discretionary

景気後退期（Recession）
├── 強い: Consumer Staples, Health Care, Utilities
└── 弱い: Financials, Consumer Discretionary, Industrials
```

### 景気サイクルの判定指標

| 指標 | 回復期 | 拡大期 | 後期 | 後退期 |
|------|--------|--------|------|--------|
| GDP成長率 | 回復中 | 高い | 鈍化 | マイナス |
| 失業率 | 低下中 | 低い | 底 | 上昇 |
| 金利 | 低い | 上昇中 | 高い | 低下中 |
| インフレ | 低い | 適度 | 高い | 低下中 |
| イールドカーブ | スティープ | フラット化 | フラット/逆転 | スティープ化 |

## 各セクターのキードライバー

### Technology（テクノロジー）
- **上昇要因**: 金利低下、企業IT投資増、AI/クラウド需要
- **下落要因**: 金利上昇、規制強化（独禁法）、バリュエーション過大
- **注目指標**: 半導体受注、クラウド支出、PER水準

### Financials（金融）
- **上昇要因**: 金利上昇（NIM拡大）、景気拡大（ローン需要）
- **下落要因**: 金利低下、景気後退（不良債権増）、金融規制
- **注目指標**: イールドカーブ傾斜、銀行融資残高、信用スプレッド

### Energy（エネルギー）
- **上昇要因**: 原油価格上昇、地政学リスク、供給制約
- **下落要因**: 原油価格下落、再生エネルギー拡大、ESG投資
- **注目指標**: WTI原油価格、OPEC生産量、米国リグカウント

### Health Care（ヘルスケア）
- **上昇要因**: 高齢化、新薬承認、M&A活動
- **下落要因**: 薬価規制、FDA審査厳格化、特許切れ
- **注目指標**: FDA承認状況、メディケア政策、パイプライン

### Consumer Discretionary（一般消費財）
- **上昇要因**: 消費者信頼感上昇、雇用好調、賃金上昇
- **下落要因**: 景気後退、消費者信頼感低下、金利上昇
- **注目指標**: 消費者信頼感指数、小売売上高、個人消費支出

## セクター分析の実践手順

```
1. マクロ環境の確認
   → 景気サイクルのどこにいるか判定

2. セクターETFのパフォーマンス比較
   → 直近1ヶ月/3ヶ月/6ヶ月のリターンを比較
   → 相対強度（RS）を計算

3. セクター固有のドライバー確認
   → 各セクターのキードライバーが現在どうなっているか

4. セクター選択
   → 景気サイクル × パフォーマンス × ドライバー で絞り込み
   → ロング候補: 強いセクター 2-3個
   → ショート候補（必要な場合）: 弱いセクター 1-2個
```

### Pythonでのセクターパフォーマンス比較

```python
import yfinance as yf
import pandas as pd

sector_etfs = {
    'Technology': 'XLK', 'Health Care': 'XLV',
    'Financials': 'XLF', 'Consumer Disc.': 'XLY',
    'Communication': 'XLC', 'Industrials': 'XLI',
    'Consumer Staples': 'XLP', 'Energy': 'XLE',
    'Utilities': 'XLU', 'Real Estate': 'XLRE',
    'Materials': 'XLB'
}

performances = {}
for sector, etf in sector_etfs.items():
    data = yf.download(etf, period='3mo', progress=False)
    ret = (data['Close'].iloc[-1] / data['Close'].iloc[0] - 1) * 100
    performances[sector] = round(ret, 2)

# パフォーマンス順にソート
sorted_perf = sorted(performances.items(), key=lambda x: x[1], reverse=True)
for sector, ret in sorted_perf:
    print(f"{sector:20s}: {ret:+.2f}%")
```
