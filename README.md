# E2E データ基盤デモ

材料研究の実験データを題材に、Databricksで **ETL → 分析 → ML → App** が一つの基盤で完結することを示すデモ環境です。

## デモ構成

```
[S3/Volume] CSVアップロード
  ↓
[ETL] Bronze → Silver → Gold（Lakeflow Declarative Pipelines）
  ↓
[Dashboard] 実験進捗ダッシュボード（AI/BI Dashboard）
  ↓
[ML] 物性値予測モデル（MLflow）
  ↓
[App] 研究者向け予測アプリ（Databricks App）
```

## ディレクトリ構造

```
.
├── data/                    # サンプルデータ（実験CSV 10,000行）
├── src/                     # Lakeflow Declarative Pipelines定義
├── notebooks/               # セットアップ・ML学習・モデルサービング
├── dashboards/              # AI/BI Dashboard定義
├── app/                     # Databricks App（FastAPI + React）
├── resources/               # Databricks Asset Bundle リソース定義
├── scripts/                 # データ生成スクリプト
└── databricks.yml           # Bundle設定
```

## サンプルデータ

| カラム | 説明 |
|--------|------|
| experiment_id | 実験ID（EXP-00001形式） |
| experiment_date | 実験実施日 |
| material_a_ratio | 材料A配合比率（0.1〜0.9） |
| material_b_ratio | 材料B配合比率（= 1 - A） |
| temperature | 温度（℃）150〜250 |
| pressure | 圧力（MPa）30〜100 |
| tensile_strength | 引張強度 |
| elongation | 伸び率 |
| hardness | 硬度 |
| result_grade | 判定結果（A/B/C） |

## セットアップ

```bash
# Python環境
uv sync

# サンプルデータ生成
uv run scripts/generate_data.py

# Databricksへのデプロイ
databricks bundle deploy -t dev
databricks bundle run -t dev setup_job
```

## 前提

- Databricks ワークスペース（Unity Catalog有効）
- Python 3.9+
- Databricks CLI v0.200+
