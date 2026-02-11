# QUANT レビュー v3: シグナル設計観点からの深掘り改善提案

> 「バックテストで検証できるか？」 -- v2で測定基盤の設計は整った。v3では検証プロトコルの具体化と統計的厳密性を追求する。

---

## エグゼクティブサマリー

v2レビューで提案したLLMセンチメント精度の測定基盤、階層フィルター方式、ベイズ的アプローチ、キャリブレーション設計は全てstrategy.mdに反映された。v2の「設計」は整った。しかし、v3の視点で見ると**設計と実装の間のギャップ**が依然として大きい。Phase 0のバックテストは「やる」とだけ書いてあり、Pythonコードの骨格もデータパイプラインも存在しない。LLMセンチメント vs FinBERT/VADERの比較実験は、同一データセットで厳密に制御された条件でなければ意味がないが、そのプロトコルが未定義。階層フィルター方式のtech_scoreのnormalize()関数は、正規化手法（min-max? z-score? percentile rank?）によって結果が劇的に変わるにもかかわらず選択基準が示されていない。ベイズ的アプローチの事前分布SR ~ Normal(0, 0.5)は直感的に妥当だが、事前分布の選択が事後推論に与える影響の感度分析がない。LLMキャリブレーションのPlatt Scalingは1行で言及されているだけで、実装の具体化がゼロ。多重比較補正はBonferroniのみだが、保守的すぎてType IIエラー（見逃し）を増大させるリスクがある。

v3では、これらの「設計したが具体化していない」項目を、**バックテストで検証できる**レベルまで落とし込む。

---

## v2からの残課題と新規論点

### 論点1: Phase 0バックテストの具体的実装設計

#### 現状の問題

strategy.mdのPhase 0には「過去決算100件でClaude CLIの方向予測精度を測定」「4,000件で大規模検証」と記載されているが、以下が完全に未定義:

- データ取得パイプライン（どのAPIで何を取得し、どう前処理するか）
- LLMへのプロンプト設計（バックテスト用と本番用で同一か？）
- ラベリングの自動化（5営業日後リターンの算出、閾値適用、ラベル付与）
- 実験の再現性保証（同一プロンプト+同一データで再実行して同じ結果が出るか）
- コスト管理（4,000件 x $0.03 = $120だが、リトライ・エラー分は？）
- 結果の保存形式と分析パイプライン

「バックテストで検証できるか？」 -- できるが、**今のままではバックテストを実行するためのコードを書くことすらできない**。仕様がないからだ。

#### 改善提案

Phase 0バックテストのPythonコード骨格を以下に定義する:

```python
# phase0/backtest_sentiment.py -- Phase 0 バックテスト骨格

import json
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

# ===== Step 1: データ収集 =====
def collect_earnings_data(start_date: str, end_date: str) -> pd.DataFrame:
    """
    過去の決算発表データを収集する。

    データソース:
    - yfinance: 決算日、EPS実績/予想、売上実績/予想
    - Alpaca News API: 決算関連ニュース（バックテスト用に保存済みデータを使用）

    出力カラム:
    - symbol, earnings_date, eps_actual, eps_estimate, eps_surprise_pct
    - revenue_actual, revenue_estimate, revenue_surprise_pct
    - price_day0_close, price_day1_close, price_day5_close
    - return_day1_pct, return_day5_pct
    - gold_label (positive / negative / neutral)
    """
    # yfinanceで S&P500 構成銘柄の決算データを取得
    # 注: yfinanceの earnings_dates は過去分も取得可能
    pass

def label_gold_standard(return_5d: float, threshold: float = 0.01) -> str:
    """
    ゴールドスタンダードラベルの付与。
    閾値の感度分析: threshold = [0.005, 0.01, 0.015, 0.02] で全て実行。
    """
    if return_5d > threshold:
        return "positive"
    elif return_5d < -threshold:
        return "negative"
    else:
        return "neutral"

# ===== Step 2: LLMセンチメント分析（バッチ実行） =====
def run_llm_sentiment_batch(
    earnings_df: pd.DataFrame,
    prompt_template: str,
    batch_size: int = 10,
    delay_between_batches: float = 2.0,
    max_retries: int = 3
) -> pd.DataFrame:
    """
    過去の決算データに対してClaude CLIでセンチメント分析を実行。

    重要な設計判断:
    1. プロンプトはバックテスト用と本番用で同一にする（バイアス防止）
    2. 各実行の入力データ・出力結果・タイムスタンプを全て保存する（再現性）
    3. バッチ実行でレートリミットを回避する
    4. エラー時はリトライし、3回失敗した場合はスキップしてログに記録

    コスト管理:
    - 100件バッチ: 推定 $3-5（リトライ込み）
    - 4,000件バッチ: 推定 $130-150（リトライ込み）
    - 中間保存: 50件ごとにJSONファイルに保存（途中再開可能）
    """
    pass

# ===== Step 3: ベースライン比較 =====
def run_finbert_baseline(texts: list[str]) -> list[dict]:
    """FinBERTでセンチメント分析（ローカル実行、コスト$0）"""
    # from transformers import pipeline
    # finbert = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    pass

def run_vader_baseline(texts: list[str]) -> list[dict]:
    """VADERでセンチメント分析（ローカル実行、コスト$0）"""
    # from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    pass

# ===== Step 4: 統計検定 =====
def compute_metrics(predictions: list, gold_labels: list) -> dict:
    """
    測定指標の算出:
    - directional_accuracy: 方向性精度
    - confidence_weighted_accuracy: 確信度加重精度
    - confusion_matrix: 3x3混同行列
    - precision_per_class, recall_per_class, f1_per_class
    - chi_squared_vs_random: ランダム判定との差のカイ二乗検定
    - chi_squared_vs_naive: 「常にポジティブ」との差のカイ二乗検定
    """
    pass

def compare_models(llm_results, finbert_results, vader_results, gold_labels) -> dict:
    """
    McNemar検定でモデル間の有意差を検定する。
    カイ二乗検定だけでは不十分。McNemar検定は「同一データセットに対する
    2つの分類器の不一致パターン」を検定するため、ペアワイズ比較に最適。
    """
    pass

# ===== Step 5: 結果レポート =====
def generate_phase0_report(metrics: dict, output_path: str):
    """
    Go/No-Go判断付きレポートをMarkdownで出力。
    判断基準:
    - LLM方向予測精度 >= 60% AND FinBERT/VADERを有意に上回る → Go
    - 上記を満たさない → No-Go（プロジェクト根本見直し）
    """
    pass
```

**データソースとコストの詳細見積もり:**

| データ | ソース | コスト | 取得方法 |
|--------|--------|--------|---------|
| 決算日・EPS/売上 | yfinance | $0 | `Ticker.earnings_dates`, `Ticker.quarterly_earnings` |
| 株価（OHLCV） | yfinance or Alpaca | $0 | 日足データ |
| 決算関連ニュース | Alpaca News API | $0（無料枠） | `GET /v1beta1/news?symbols=AAPL&start=...` |
| LLMセンチメント（100件） | Claude API | $3-5 | subprocess + claude CLI |
| LLMセンチメント（4,000件） | Claude API | $130-150 | バッチ実行、中間保存付き |
| FinBERT | HuggingFace（ローカル） | $0 | `ProsusAI/finbert` |
| VADER | Python パッケージ | $0 | `vaderSentiment` |

**実行計画:**

| Step | 内容 | 所要時間 | コスト |
|------|------|---------|--------|
| 1 | データ収集（yfinance + Alpaca News） | 2-4時間 | $0 |
| 2 | ゴールドスタンダードラベル付与 | 30分 | $0 |
| 3a | LLM 100件パイロット | 1-2時間 | $3-5 |
| 3b | FinBERT + VADER 100件 | 30分 | $0 |
| 4 | パイロット結果分析・Go/No-Go（小） | 1時間 | $0 |
| 5 | LLM 4,000件フル実行（Go判定の場合） | 8-12時間 | $130-150 |
| 6 | フル結果分析・最終Go/No-Go | 2時間 | $0 |

#### 検証方法

バックテストで検証できるか？ -- **上記のコード骨格とデータパイプラインを使えば、Phase 0の全項目が再現可能な形で検証できる。** パイロット100件の結果で方向性を確認し、フル4,000件に進むかどうかのステージゲートを設ける。パイロットで精度55%未満なら4,000件に進む意味はない。

---

### 論点2: LLMセンチメント vs FinBERT/VADER 比較実験プロトコル

#### 現状の問題

strategy.mdに「FinBERT/VADERとの差が+5%以上」という合格基準があるが、比較実験のプロトコルが未定義。公正な比較のためには以下の制御が必要:

1. **入力データの同一性**: LLMには決算ニュースのフルテキスト、FinBERTにはヘッドラインのみ、という不公平な比較になっていないか？
2. **タスク定義の同一性**: LLMは3クラス分類（positive/negative/neutral）だが、FinBERTもVADERも出力形式が異なる。どう統一するか？
3. **確信度の比較可能性**: LLMの「確信度85%」とFinBERTの「positive score 0.85」は直接比較できない。
4. **統計検定の選択**: カイ二乗検定だけで十分か？McNemar検定が適切ではないか？

#### 改善提案

**比較実験プロトコル（厳密版）:**

```
1. 入力データの統一:
   - 全モデルに同一のニューステキストを入力する
   - 入力テキストの長さ制限:
     * LLM: フルテキスト（最大2,000 tokens）
     * FinBERT: 同じフルテキストを512 tokensに切断（FinBERTの最大長）
     * VADER: 同じフルテキスト全体
   - 注: FinBERTのトークン制限による情報損失は「モデルの特性」として記録する

2. 出力形式の統一:
   全モデルの出力を以下の共通フォーマットに変換する:
   {
     "label": "positive" | "negative" | "neutral",
     "confidence": 0.0-1.0,  # 各モデルのスコアを[0,1]に正規化
     "raw_output": { ... }    # 元の出力を保存（事後分析用）
   }

   変換ルール:
   - FinBERT: argmax(positive, negative, neutral) → label, max score → confidence
   - VADER: compound > 0.05 → positive, < -0.05 → negative, else neutral
             |compound| → confidence（ただし感度分析で閾値0.03, 0.05, 0.10を比較）
   - LLM: プロンプトで直接3クラス+確信度を出力させる

3. 評価指標（全モデル共通）:
   - プライマリ: 方向性精度（Directional Accuracy）
   - セカンダリ: F1-macro（クラス不均衡への対処）
   - 確信度評価: Brier Score（キャリブレーション品質の定量指標）
   - 経済的価値: 各モデルのシグナルに従って仮想売買した場合のシャープレシオ

4. 統計検定:
   - モデル間比較: McNemar検定（ペアワイズ。同一データセットでの分類器比較に最適）
   - ランダムベースライン: カイ二乗検定
   - 確信度キャリブレーション: Hosmer-Lemeshow検定
   - 効果量: Cohen's kappa（モデル間の一致度）

5. サンプルサイズの事前計算:
   McNemar検定で効果量(不一致率の差)10%を検出するために必要なサンプルサイズ:
   n >= (z_alpha + z_beta)^2 / (p_discordant * effect_size^2)
   概算: 有意水準5%, 検出力80%で約200件
   → パイロット100件では検出力が不足する可能性がある
   → 200件に増やすか、パイロットは方向性確認にとどめる
```

**追加提案: LLMの公正性担保**

FinBERT/VADERは事前学習済みモデルで追加コスト$0だが、LLMはプロンプトによって性能が大きく変動する。「LLMが優れている」という結論が「このプロンプトが優れている」に過ぎない可能性がある。対策:

- LLMのプロンプトを3種類（簡潔版、詳細版、Chain-of-Thought版）用意し、全てのプロンプトでFinBERT/VADERを上回ることを要求する
- 最低1つのプロンプトバリエーションでFinBERT/VADERとの有意差が出なければ、LLMのエッジは「プロンプトに過剰適合」と判断する

#### 検証方法

バックテストで検証できるか？ -- 上記プロトコルに従えば、厳密に検証可能。McNemar検定は`statsmodels`パッケージの`mcnemar()`関数で1行で実行できる。Brier Scoreは`sklearn.metrics.brier_score_loss()`で算出可能。問題は実行コストと時間であり、LLM 3プロンプト x 200件 = 600回のAPI呼び出し（$18-20）が必要。Phase 0の予算$120内に十分収まる。

---

### 論点3: 階層フィルター方式のtech_score正規化手法

#### 現状の問題

strategy.md Stage 2に以下の記載がある:

```
tech_score = normalize(ma_distance) + normalize(rsi_neutral) + normalize(volume_ratio)
```

この`normalize()`関数の実装が未定義であり、正規化手法の選択によってランキング結果が劇的に変わる:

| 正規化手法 | 特性 | 問題点 |
|-----------|------|--------|
| Min-Max | [0,1]に線形圧縮 | 外れ値に極めて敏感。1銘柄の異常値がスコア全体を歪める |
| Z-Score | 平均0、標準偏差1 | 正規分布を仮定。出来高比率は右に歪む分布 |
| Percentile Rank | [0,1]の順位パーセンタイル | 外れ値に頑健。ただし銘柄数が少ないと解像度が低い |
| Robust Scaling | 中央値と四分位範囲 | 外れ値に頑健。Z-Scoreの頑健版 |

さらに、3つのスコアを単純加算する場合、各コンポーネントに等しい重みを暗黙に仮定している。ma_distanceが最も重要か、volume_ratioが最も重要か、は仮定に過ぎない。

#### 改善提案

```python
# 正規化手法の比較実験

import numpy as np
from scipy import stats

def normalize_minmax(values: np.ndarray) -> np.ndarray:
    """Min-Max正規化。外れ値にはwinsorize前処理を適用。"""
    # 1%/99%パーセンタイルでwinsorize（外れ値の影響を緩和）
    lower = np.percentile(values, 1)
    upper = np.percentile(values, 99)
    clipped = np.clip(values, lower, upper)
    return (clipped - clipped.min()) / (clipped.max() - clipped.min() + 1e-8)

def normalize_percentile(values: np.ndarray) -> np.ndarray:
    """パーセンタイルランク正規化。推奨手法。"""
    return stats.rankdata(values, method='average') / len(values)

def normalize_robust(values: np.ndarray) -> np.ndarray:
    """ロバストスケーリング（中央値・IQR基準）。"""
    median = np.median(values)
    iqr = np.percentile(values, 75) - np.percentile(values, 25)
    return (values - median) / (iqr + 1e-8)

# 推奨: パーセンタイルランクを基本とする
# 理由:
# 1. 外れ値に頑健
# 2. 分布の形状に依存しない
# 3. 解釈が容易（「上位20%以内」等）
# 4. 銘柄数30-80の範囲で十分な解像度がある

# tech_scoreの計算
def compute_tech_score(
    ma_distances: np.ndarray,
    rsi_values: np.ndarray,
    volume_ratios: np.ndarray,
    weights: tuple = (0.4, 0.3, 0.3)  # 重みは感度分析の対象
) -> np.ndarray:
    """
    テクニカルスコアの計算。

    重み付けの根拠:
    - ma_distance (0.4): トレンド方向がPEADの最重要ファクター
    - rsi_neutral (0.3): 過熱/売られすぎの回避
    - volume_ratio (0.3): 制度的投資家の参加度の代理指標

    感度分析: weights = [(0.33,0.33,0.34), (0.5,0.25,0.25),
                         (0.4,0.3,0.3), (0.25,0.25,0.5)]
    """
    w_ma, w_rsi, w_vol = weights

    norm_ma = normalize_percentile(ma_distances)

    # RSIは「70に近いほど悪い」ため反転させる
    rsi_neutral_score = 1.0 - normalize_percentile(np.abs(rsi_values - 50))

    norm_vol = normalize_percentile(volume_ratios)

    return w_ma * norm_ma + w_rsi * rsi_neutral_score + w_vol * norm_vol
```

**重み付けの決定方法（v3新規提案）:**

重みを人手で決定するのはパラメータ増加と同義であり、オーバーフィッティングリスクがある。代替案として以下を検討:

1. **等重み（ベースライン）**: w = (0.33, 0.33, 0.34)。追加のパラメータなし
2. **情報量ベース**: 各コンポーネントと5日後リターンの相互情報量（Mutual Information）に比例した重み付け。Phase 0のデータで算出可能
3. **全パターン比較**: 重みの組み合わせ4パターンでバックテストし、ウォークフォワードで最良のパターンを選定

推奨は「等重みでスタートし、6ヶ月運用後にデータに基づいて重みを1回だけ調整する」方式。初期段階で重みを最適化すると、少ないサンプルへのオーバーフィッティングが確実に起きる。

#### 検証方法

バックテストで検証できるか？ -- 完全に可能。正規化手法4種 x 重みパターン4種 = 16パターンのグリッドサーチを、Phase 0のデータ（4,000件）でウォークフォワードテストする。ただし16パターンの比較は多重比較問題が発生するため、Bonferroni補正（有意水準 0.05/16 = 0.003）を適用して「偶然のベスト」を排除する。

---

### 論点4: 時系列クロスバリデーション（TimeSeriesSplit）の具体的設計

#### 現状の問題

v2レビューで「TimeSeriesSplitによるクロスバリデーション」を提案し、strategy.mdのセクション7に「時系列クロスバリデーション」の言及があるが、具体的な設計が以下の点で不足している:

1. **Split数とウィンドウサイズの選定根拠がない**: 「5-fold、各foldの学習期間は最低6ヶ月」と書いたが、なぜ5-foldか？なぜ6ヶ月か？
2. **Expanding Window vs Sliding Window の選択が未定**: Expanding Windowは学習データが増え続けるため安定性が高いが、レジームチェンジへの適応が遅い。Sliding Windowは最新のデータのみを使うが、サンプル数が固定
3. **パージ（Purge）とエンバーゴ（Embargo）の考慮がない**: 金融時系列CVではデータリーケージ防止のため、学習データとテストデータの間に「パージ期間」を設ける必要がある（Lopez de Prado, 2018）
4. **レジーム依存性の検証がない**: ブル相場のみの学習データでベア相場をテストすると、パフォーマンスが劇的に劣化する。レジーム別の検証が必要

#### 改善提案

```python
# 時系列クロスバリデーションの具体設計

from sklearn.model_selection import TimeSeriesSplit
import numpy as np

class PurgedTimeSeriesSplit:
    """
    金融時系列向けクロスバリデーション。

    Lopez de Prado (2018) のCombinatorial Purged Cross-Validationを
    簡略化した実装。

    パラメータ:
    - n_splits: フォールド数（推奨: 5）
    - train_period_days: 学習期間（推奨: 252日 = 1年）
    - test_period_days: テスト期間（推奨: 63日 = 3ヶ月）
    - purge_days: パージ期間（推奨: 10日）
    - embargo_days: エンバーゴ期間（推奨: 5日）
    """

    def __init__(
        self,
        n_splits: int = 5,
        train_period_days: int = 252,
        test_period_days: int = 63,
        purge_days: int = 10,  # 学習/テスト間のバッファ（リーケージ防止）
        embargo_days: int = 5   # テスト期間後のバッファ
    ):
        self.n_splits = n_splits
        self.train_period_days = train_period_days
        self.test_period_days = test_period_days
        self.purge_days = purge_days
        self.embargo_days = embargo_days

    def split(self, dates: np.ndarray):
        """
        Expanding Windowを基本とし、パージとエンバーゴを適用。

        |<-- train -->|<purge>|<-- test -->|<embargo>|
        |<----- train ----->|<purge>|<-- test -->|<embargo>|

        各foldの構造:
        Fold 1: [2022-01 ~ 2022-12] purge [2023-01 ~ 2023-03]
        Fold 2: [2022-01 ~ 2023-03] purge [2023-04 ~ 2023-06]
        Fold 3: [2022-01 ~ 2023-06] purge [2023-07 ~ 2023-09]
        Fold 4: [2022-01 ~ 2023-09] purge [2023-10 ~ 2023-12]
        Fold 5: [2022-01 ~ 2024-01] purge [2024-02 ~ 2024-04]

        注: Expanding Windowを採用する理由:
        - 学習データが増えるにつれてモデルの安定性が向上
        - Sliding Windowは「過去のデータを捨てる」ため、
          レジーム変化の学習機会を失う
        - ただし、3年以上のデータではSlidingも検討すべき
          （古いデータのレジームが現在と乖離しすぎる場合）
        """
        pass

# 推奨パラメータの根拠:
#
# n_splits = 5:
#   3年データ（756営業日）を使う場合、train=252日、test=63日、
#   purge=10日、embargo=5日で、5フォールドが最大
#   3年未満のデータでは n_splits=3 に縮小
#
# purge_days = 10:
#   この戦略の最大保有期間が10日であるため、
#   学習データの最後のトレードがテスト期間に影響しないよう10日のパージ
#
# embargo_days = 5:
#   テスト期間のトレードが次のフォールドの学習に影響しないよう5日
```

**レジーム別パフォーマンスの検証（v3新規提案）:**

```
全フォールドの平均パフォーマンスだけでなく、各フォールドの
テスト期間のマクロレジームを記録し、以下を報告する:

| Fold | テスト期間 | レジーム | SR | 勝率 | 取引数 |
|------|----------|----------|-----|------|--------|
| 1 | 2023 Q1 | ブル | ? | ? | ? |
| 2 | 2023 Q2 | ブル | ? | ? | ? |
| 3 | 2023 Q3 | レンジ | ? | ? | ? |
| 4 | 2023 Q4 | ブル | ? | ? | ? |
| 5 | 2024 Q1 | ブル | ? | ? | ? |

警告: 5フォールド中4フォールドがブル相場の場合、
「平均SR > 0.5」は「ブル相場でロングが儲かった」を意味するだけ。
ベア/レンジのフォールドが1つもなければ、ロバストネスの主張はできない。

対策: 2022年のデータを強制的にテスト期間に含むフォールドを
1つ以上設計する（ベアレジーム検証の保証）。
```

#### 検証方法

バックテストで検証できるか？ -- 完全に可能。`PurgedTimeSeriesSplit`クラスの実装は100行程度。`sklearn`の`TimeSeriesSplit`をベースに、パージとエンバーゴのロジックを追加するだけ。各フォールドのパフォーマンスのバラツキ（標準偏差）が平均の50%を超える場合は「ロバストネス不足」と判断し、パラメータの見直しを行う。

---

### 論点5: ベイズ的アプローチの事前分布設計とMAP推定の実装

#### 現状の問題

strategy.mdに以下の記載がある:

```
事前分布: SR ~ Normal(0, 0.5)（スキルなしが事前の期待）
事後分布: 取引結果で更新
リアル移行条件: 事後確率 P(SR > 0.5 | data) > 90%
```

この設計には以下の未解決点がある:

1. **事前分布Normal(0, 0.5)の根拠が薄い**: なぜ標準偏差0.5か？0.3なら事前が強すぎて（少ないデータでは事前分布に引きずられる）、1.0なら事前が弱すぎる（ほぼ無情報事前分布で、頻度主義と変わらない）
2. **更新メカニズムの未定義**: 「取引結果で更新」とはどういう計算か？共役事前分布を使うのか、MCMCを使うのか
3. **事前分布の感度分析がない**: 事前分布の選択が結論（Go/No-Go）に影響しないことを示す必要がある
4. **情報提供事前分布の検討がない**: 既存のPEAD研究のメタ分析からSRの事前分布を推定できる可能性

#### 改善提案

```python
# ベイズ推定の具体的実装

import numpy as np
from scipy import stats

class BayesianSharpeEstimator:
    """
    シャープレシオのベイズ推定器。

    モデル:
    - 日次リターン r_i ~ Normal(mu, sigma^2)
    - SR = mu / sigma * sqrt(252)  （年率換算）
    - 事前分布: mu ~ Normal(mu_0, tau_0^2)
    - sigma^2 は既知と仮定（サンプル分散で代用）

    これは共役事前分布（正規-正規モデル）であり、
    事後分布が解析的に求まる。MCMCは不要。
    """

    def __init__(
        self,
        prior_sr_mean: float = 0.0,
        prior_sr_std: float = 0.5
    ):
        """
        事前分布の設定。

        prior_sr_mean = 0.0: 「スキルなし」が事前の期待
        prior_sr_std = 0.5: PEAD戦略の文献レビューに基づく
          - Bernard & Thomas (1989): PEAD SR ≈ 0.5-0.8
          - 最近の研究: α縮小傾向でSR ≈ 0.3-0.5
          - 標準偏差0.5は「SR=-0.5からSR=+0.5の範囲に68%の確率」を意味
          - 現実的に「少しだけスキルがある可能性」を許容する事前
        """
        # SRからmu（日次平均リターン）に変換
        # SR = mu / sigma * sqrt(252), assuming sigma ≈ 0.015 (typical for daily returns)
        self.typical_sigma = 0.015  # 日次リターンの典型的な標準偏差
        self.prior_mu_mean = prior_sr_mean * self.typical_sigma / np.sqrt(252)
        self.prior_mu_var = (prior_sr_std * self.typical_sigma / np.sqrt(252)) ** 2

    def update(self, daily_returns: np.ndarray) -> dict:
        """
        取引データで事後分布を更新する。

        共役事前分布の更新公式:
        posterior_mu = (prior_mu / prior_var + n * sample_mean / sample_var)
                       / (1/prior_var + n/sample_var)
        posterior_var = 1 / (1/prior_var + n/sample_var)
        """
        n = len(daily_returns)
        sample_mean = np.mean(daily_returns)
        sample_var = np.var(daily_returns, ddof=1)

        # 事後分布の計算
        posterior_precision = 1/self.prior_mu_var + n/sample_var
        posterior_var = 1 / posterior_precision
        posterior_mean = posterior_var * (
            self.prior_mu_mean / self.prior_mu_var +
            n * sample_mean / sample_var
        )

        # SRに変換
        posterior_sr_mean = posterior_mean / np.sqrt(sample_var) * np.sqrt(252)
        posterior_sr_std = np.sqrt(posterior_var) / np.sqrt(sample_var) * np.sqrt(252)

        # P(SR > 0.5 | data) の計算
        prob_sr_above_05 = 1 - stats.norm.cdf(
            0.5, loc=posterior_sr_mean, scale=posterior_sr_std
        )

        return {
            "posterior_sr_mean": posterior_sr_mean,
            "posterior_sr_std": posterior_sr_std,
            "posterior_sr_95ci": (
                posterior_sr_mean - 1.96 * posterior_sr_std,
                posterior_sr_mean + 1.96 * posterior_sr_std
            ),
            "prob_sr_above_0": 1 - stats.norm.cdf(0, posterior_sr_mean, posterior_sr_std),
            "prob_sr_above_05": prob_sr_above_05,
            "n_observations": n,
            "sample_sr": sample_mean / np.sqrt(sample_var) * np.sqrt(252),
        }

    def sensitivity_analysis(self, daily_returns: np.ndarray) -> dict:
        """
        事前分布の感度分析。
        3つの事前分布で結果がどう変わるかを報告する。

        結果が事前分布に大きく依存する場合 → データ不足。判断を延期すべき。
        結果が事前分布にほぼ依存しない場合 → データが十分。判断可能。
        """
        priors = [
            ("懐疑的", 0.0, 0.3),   # 狭い事前: 強くスキルなしを信じる
            ("中立的", 0.0, 0.5),   # 基本の事前
            ("楽観的", 0.2, 0.7),   # 広い事前: やや楽観的
        ]
        results = {}
        for name, sr_mean, sr_std in priors:
            estimator = BayesianSharpeEstimator(sr_mean, sr_std)
            results[name] = estimator.update(daily_returns)

        # 判断基準: 3つの事前全てでP(SR>0.5|data)>80%なら「事前に頑健」
        # 事前によって50%以上の差がある場合は「データ不足」
        return results
```

**月次の事後分布更新レポートの雛形:**

```
=== ベイズ推定月次レポート（Month 3） ===

取引数: 45件（累計）
サンプルSR: 0.72

事後分布（中立的事前）:
  事後SR平均: 0.48
  事後SR 95%CI: [-0.12, 1.08]
  P(SR > 0) = 94.5%
  P(SR > 0.5) = 46.2%  ← リアル移行条件(90%)に未到達

事前分布感度分析:
  懐疑的事前: P(SR>0.5) = 38.1%
  中立的事前: P(SR>0.5) = 46.2%
  楽観的事前: P(SR>0.5) = 55.7%
  → 事前分布による差: 17.6% → データがまだ不足。判断延期。

次月の予測:
  月15取引ペースで、サンプルSRが0.72を維持する場合、
  Month 6時点でP(SR>0.5|data) ≈ 72%（推定）
  Month 9時点でP(SR>0.5|data) ≈ 85%（推定）
  Month 12時点でP(SR>0.5|data) ≈ 91%（推定） ← 条件達成見込み
```

#### 検証方法

バックテストで検証できるか？ -- `BayesianSharpeEstimator`クラスはバックテストデータの日次リターンを入力として、事後分布を計算する。事前分布の感度分析により、「結論が事前分布に依存する（=データ不足）」か「結論が事前分布に頑健（=データ十分）」かを定量的に判断できる。シミュレーションで「真のSR=0.5の戦略が、何ヶ月でP(SR>0.5|data)>90%に到達するか」を事前に推定すべき（推定: 月15取引で10-14ヶ月）。

---

### 論点6: LLMキャリブレーションのPlatt Scaling実装の具体化

#### 現状の問題

strategy.mdに「必要に応じてPlatt Scalingで確信度を補正」と記載されているが、以下が未定義:

1. **Platt Scalingの学習データはどこから来るか？** キャリブレーションを行うには「LLMの確信度 → 実際の的中率」のペアが必要だが、これは運用開始後のデータでしか得られない。鶏卵問題。
2. **最小サンプルサイズ**: Platt Scalingのロジスティック回帰は最低何件のデータで安定するか？
3. **更新頻度**: 月次？それとも取引50件ごと？
4. **Isotonic Regressionとの比較**: Platt Scaling（パラメトリック）は仮定が強い。Isotonic Regression（ノンパラメトリック）の方が柔軟だが、サンプルが少ないとオーバーフィットする。

#### 改善提案

```python
# キャリブレーション実装

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve

class ConfidenceCalibrator:
    """
    LLM確信度のキャリブレーション。

    Phase 0のデータを初期キャリブレーションに使用し、
    運用開始後は月次でオンライン更新する。

    鶏卵問題の解決:
    1. Phase 0の100-200件でパイロットキャリブレーションを構築
    2. Phase 5の最初の1ヶ月は「キャリブレーションなし」で運用
       （確信度閾値70%はそのまま適用）
    3. 1ヶ月目終了時（約30-60件のデータ）で初回キャリブレーション構築
    4. 以後、月次で再キャリブレーション
    """

    def __init__(self, method: str = "platt"):
        """
        method: "platt" (Platt Scaling) or "isotonic" (Isotonic Regression)

        推奨:
        - n < 100: Platt Scaling（パラメータ2つで安定）
        - n >= 100: Isotonic Regression（柔軟だがデータ量が必要）
        """
        self.method = method
        if method == "platt":
            self.model = LogisticRegression(C=1.0)
        else:
            self.model = IsotonicRegression(out_of_bounds="clip")
        self.is_fitted = False

    def fit(self, raw_confidences: np.ndarray, actual_outcomes: np.ndarray):
        """
        キャリブレーションモデルの学習。

        raw_confidences: LLMが出力した確信度 [0, 1]
        actual_outcomes: 実際の的中フラグ {0, 1}

        最小サンプルサイズ:
        - Platt Scaling: 最低50件（推奨100件）
        - Isotonic Regression: 最低100件（推奨200件）
        """
        if len(raw_confidences) < 50:
            raise ValueError(
                f"サンプル数{len(raw_confidences)}はキャリブレーションに不足。"
                "最低50件必要。"
            )

        if self.method == "platt":
            self.model.fit(raw_confidences.reshape(-1, 1), actual_outcomes)
        else:
            self.model.fit(raw_confidences, actual_outcomes)
        self.is_fitted = True

    def calibrate(self, raw_confidence: float) -> float:
        """補正後の確信度を返す。"""
        if not self.is_fitted:
            return raw_confidence  # キャリブレーション前は生の値を返す

        if self.method == "platt":
            return self.model.predict_proba(
                np.array([[raw_confidence]])
            )[0, 1]
        else:
            return self.model.predict(np.array([raw_confidence]))[0]

    def reliability_diagram(
        self, raw_confidences: np.ndarray, actual_outcomes: np.ndarray
    ) -> dict:
        """
        信頼性図（Reliability Diagram）のデータを生成。

        ビンごとの「LLM確信度の平均」vs「実際の的中率」をプロット。
        完全キャリブレーション = 対角線上に点が並ぶ。
        """
        bins = np.arange(0.5, 1.05, 0.1)  # [0.5-0.6, 0.6-0.7, ..., 0.9-1.0]
        fraction_positive, mean_predicted = calibration_curve(
            actual_outcomes, raw_confidences, n_bins=5, strategy='uniform'
        )

        # Expected Calibration Error (ECE)
        bin_counts = np.histogram(raw_confidences, bins=bins)[0]
        ece = np.sum(
            bin_counts / len(raw_confidences) *
            np.abs(fraction_positive - mean_predicted)
        )

        return {
            "bin_centers": mean_predicted.tolist(),
            "actual_accuracy": fraction_positive.tolist(),
            "bin_counts": bin_counts.tolist(),
            "ece": float(ece),  # < 0.05 が目標
        }
```

**キャリブレーション運用のタイムライン:**

| 時期 | データ件数 | アクション |
|------|----------|-----------|
| Phase 0 | 100-200件 | パイロットキャリブレーション構築。Platt Scaling |
| Phase 5 Month 1 | +30-60件 | キャリブレーションなしで運用。データ蓄積のみ |
| Phase 5 Month 2 | +30-60件 | 初回キャリブレーション更新。ECE < 0.10 を目標 |
| Phase 5 Month 3+ | +30-60件/月 | 月次再キャリブレーション。ECE < 0.05 を目標 |
| 累計100件到達 | 100件+ | Isotonic Regressionへの切替を検討 |

#### 検証方法

バックテストで検証できるか？ -- Phase 0の100-200件のデータでキャリブレーション前後の信頼性図を比較可能。ECE（Expected Calibration Error）が0.05未満に改善すれば、キャリブレーションは有効。改善しなければ、LLMの確信度をポジションサイズ調整に使う設計を再考すべき。

---

### 論点7: 多重比較補正 -- Bonferroni以外のFDR制御の検討

#### 現状の問題

strategy.mdのセクション7に以下の記載がある:

```
パラメータ変更回数をK回とする
Bonferroni補正: 有意水準 = 0.05 / K
例: 5回のパラメータ変更なら p < 0.01 で判断
```

Bonferroni補正は最も保守的な多重比較補正であり、以下の問題がある:

1. **Type IIエラー（見逃し）の増大**: K=10回の変更で有意水準0.005になると、真に有効な改善も検出できなくなる。「改善してるのに有意にならないから元に戻す」を繰り返す無限ループに陥るリスク
2. **検定の独立性仮定**: Bonferroniは検定が独立であることを仮定するが、パラメータ変更は相互に影響しうる（例: ストップロス距離を変えればテイクプロフィットの最適値も変わる）
3. **探索的分析との混同**: パラメータ変更のたびにKPIを確認するのは探索的分析（仮説生成）であり、確証的分析（仮説検定）とは区別すべき

#### 改善提案

```
1. Bonferroni → Benjamini-Hochberg (BH) 法への移行:

   BH法はFDR（False Discovery Rate）を制御する。
   Bonferroniが「1つでも偽陽性が出る確率」を制御するのに対し、
   BH法は「検出された改善のうち偽陽性の割合」を制御する。

   具体的手順:
   a. K回のパラメータ変更のp値を小さい順にソート: p_(1) <= p_(2) <= ... <= p_(K)
   b. 各p値に対して閾値を計算: threshold_(i) = (i/K) * alpha
   c. p_(i) <= threshold_(i) を満たす最大のiを求める
   d. p_(1), ..., p_(i) に対応する改善を「有効」と判断

   FDR水準: alpha = 0.10（改善のうち10%までは偽陽性を許容）

   利点:
   - Bonferroniより検出力が高い（Type IIエラーが少ない）
   - K=10でも個々の閾値は0.01-0.10の範囲（Bonferroniの0.005より緩い）
   - 「いくつかの改善は偶然かもしれないが、全体としては改善傾向がある」
     という判断が可能

2. ただし、以下の条件を追加:
   - 各パラメータ変更は最低20取引のクールダウン後に評価する
   - 評価はout-of-sample（変更後の新しいデータのみ）で行う
   - 同一パラメータの「戻し」は新たな変更としてカウントしない

3. 探索的分析と確証的分析の分離:
   - 探索的（仮説生成）: パフォーマンスダッシュボードの自由な分析。
     p値なし。「こういう傾向がありそうだ」の段階
   - 確証的（仮説検定）: 具体的なパラメータ変更→効果測定。
     BH法でFDR制御。「この変更は有効である」の判断

   混同が危険な例:
   「ダッシュボードで確信度80%以上の取引が好成績→
    閾値を80%に引き上げよう→引き上げたら好成績→有意!」
   これは「同じデータで仮説を生成し検定した」（p-hacking）のであり無効。
   変更後の新しいデータのみで検証しなければならない。
```

#### 検証方法

バックテストで検証できるか？ -- BH法自体はp値のリストを入力とする単純なアルゴリズムであり、`statsmodels.stats.multitest.multipletests(pvalues, method='fdr_bh')`で1行で実行できる。シミュレーションで「5回のパラメータ変更のうち2回が真に有効、3回がランダム」というシナリオを10,000回生成し、Bonferroni vs BH法の検出力を比較すべき。BH法の検出力がBonferroniを20%以上上回るはず。

---

### 論点8: シグナル間の情報量（Mutual Information）分析

#### 現状の問題

v2で階層フィルター方式を導入し、LLMセンチメントをプライマリ、テクニカルをセカンダリとした。しかし、以下の根本的な疑問が未解決:

1. **LLMセンチメントとテクニカル指標は独立か？** LLMはニュースの文脈を理解するが、株価変動（=テクニカル指標の基礎データ）もニュースに反応する。両者の相関が高ければ、テクニカルフィルターは「LLMが既に持っている情報の劣化版」に過ぎない
2. **テクニカルフィルターはリターン予測に追加情報を提供しているか？** LLMセンチメントが70%の予測力を持つ場合、テクニカルフィルターを追加して72%になるのか、70%のままなのか
3. **情報の冗長性はフィルター設計に影響する**: LLMとテクニカルの情報が冗長なら、テクニカルフィルターは「フィルター」ではなく「ノイズ」であり、シグナル数を減らすだけの害がある

#### 改善提案

```
1. Mutual Information（MI）分析:
   各シグナルソースと5日後リターンの相互情報量を計算する。

   MI(LLM_sentiment, return_5d) = ?
   MI(ma_distance, return_5d) = ?
   MI(rsi, return_5d) = ?
   MI(volume_ratio, return_5d) = ?

   次に、シグナル間の相互情報量を計算する:

   MI(LLM_sentiment, ma_distance) = ?
   MI(LLM_sentiment, rsi) = ?
   MI(LLM_sentiment, volume_ratio) = ?

   解釈:
   - MI(LLM, return) >> MI(tech, return): LLMが圧倒的に情報量が多い
     → テクニカルフィルターは不要かもしれない
   - MI(LLM, tech) が高い: LLMとテクニカルの情報が冗長
     → テクニカルを追加しても予測力は向上しない
   - MI(LLM, tech) が低い: LLMとテクニカルは独立の情報を持つ
     → テクニカルフィルターの追加が有効

2. Conditional Mutual Information:
   テクニカル指標が「LLMの情報に加えて」どれだけの追加情報を持つかを測定:

   CMI(tech, return | LLM) = MI(tech, return | LLM_sentiment)

   CMI ≈ 0: テクニカルはLLM以上の情報を持たない → フィルターとして不要
   CMI > 0: テクニカルはLLMの補完的情報を持つ → フィルターとして有効

3. 実装（Phase 0データで実行可能）:
   sklearn.feature_selection.mutual_info_classif() で離散MI
   sklearn.feature_selection.mutual_info_regression() で連続MI

   注意: MIの推定にはサンプルサイズ200件以上が望ましい。
   100件では推定精度が低くバイアスが大きい。
   Phase 0の4,000件データならMI分析に十分。

4. 結果に基づくフィルター設計の最適化:
   - CMI(tech|LLM) ≈ 0のテクニカル指標はフィルターから除外
   - CMI(tech|LLM) > 0のテクニカル指標のみフィルターに残す
   - 例: 出来高比率のMIが低い場合、フィルターを2条件に簡素化
     → シグナル数が増加し、取引数の確保に寄与
```

**この分析が戦略に与えるインパクトの予測:**

v2レビューで「AND条件だとシグナルが減りすぎる」問題を指摘し、階層フィルター方式に変更した。しかし、フィルター条件を3つ維持している限り、シグナル削減の問題は根本的には解決していない。MI分析により「実質的に情報を追加しないフィルター」を特定・除外できれば、シグナル数を大幅に改善できる。

例: volume_ratioのCMI(volume|LLM)がほぼゼロであれば、出来高条件を撤廃し、tech_score = normalize(ma_distance) + normalize(rsi_neutral) の2変数に簡素化。フィルター通過率が推定で30-40%向上する。

#### 検証方法

バックテストで検証できるか？ -- Phase 0の4,000件データがあれば完全に検証可能。`sklearn`のMI関数は数行で実行できる。結果をtech_score計算にフィードバックし、MI分析前後のシグナル数・パフォーマンスを比較するA/Bテストが可能。

---

## 最終提言（優先順位付き3項目）

### 1. Phase 0バックテストのコード骨格とデータパイプラインを即座に具体化せよ（最優先）

v2で「Phase 0をやる」と決めたのは正しい。しかし、「やる」と「実行可能な仕様がある」の間には巨大なギャップがある。本レビューの論点1で提示したPythonコード骨格、データソース一覧、実行計画テーブルを、action-plan.mdのPhase 0タスクリストに直接統合すべきだ。**バックテストで検証できるか？** -- コード骨格なくして検証なし。設計書に「バックテスト」と書いても、コードがなければ1行の検証も実行されない。Phase 0のWeek 1-2でコード骨格を先に書き、Week 2でデータ収集→分析を一気に実行する。パイロット100件の結果が出た時点で、フル4,000件に進むかのステージゲート判断を行う。

### 2. シグナル間のMutual Information分析を Phase 0 に組み込め

テクニカルフィルターの3条件（MA距離、RSI、出来高比率）がLLMセンチメントと「どの程度冗長か」は、Phase 0のデータで定量化できる。この分析を行わずに3条件のフィルターを実装すると、v2で指摘した「シグナル数不足」問題が再燃する。MI分析は追加コスト$0（Phase 0の既存データを再利用）で実行可能であり、フィルター設計を証拠に基づいて最適化できる唯一の手段だ。**バックテストで検証できるか？** -- MI分析こそが「フィルター設計をバックテストで検証する」行為そのものである。

### 3. ベイズ推定の事前分布感度分析を運用初日から実施せよ

ベイズ的アプローチはv2の最も重要な追加提案の一つだが、事前分布Normal(0, 0.5)が結論に与える影響を定量化しないまま運用を始めてはならない。本レビューの論点5で提示した`BayesianSharpeEstimator`クラスを実装し、**月次レポートに3つの事前分布での感度分析を必ず含める**ことを義務化すべきだ。事前分布の選択で結論が変わるうちはデータ不足であり、リアル移行の判断を下してはならない。**バックテストで検証できるか？** -- シミュレーションで「真のSR=0.5の戦略が何ヶ月で事前分布に頑健な結論に到達するか」を事前に推定できる。この推定値がペーパートレーディング期間の長さと整合しているかを確認すべきだ。

---

*「バックテストで検証できるか？」 -- v3の答えは「Yes, ただし具体的な実装仕様とプロトコルが必要」だ。設計書に検証手法を書くだけでは不十分であり、Pythonコードの骨格、データパイプライン、統計検定の選択根拠まで落とし込んで初めて「検証可能」になる。検証可能性は設計レベルで保証せよ。実装レベルの詳細は後からでは手遅れになる。*

---

*レビュー実施: QUANT（シグナル設計者）*
*レビュー日: 2026-02-11*
*対象文書: docs2/strategy.md, docs2/system-design.md, docs2/action-plan.md, docs2/planning-log.md, docs2/review-quant.md*
