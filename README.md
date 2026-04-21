# E2E データ基盤デモ on Databricks

材料研究の実験データを題材に、Databricksで **ETL → 分析 → ML → App** が一つの基盤で完結することを示すデモ環境です。

## 目次

1. [デモ構成](#デモ構成)
2. [前提条件](#前提条件)
3. [ディレクトリ構成](#ディレクトリ構成)
4. [サンプルデータ](#サンプルデータ)
5. [セットアップ手順](#セットアップ手順)
6. [デプロイ手順](#デプロイ手順)
7. [動作確認](#動作確認)
8. [カスタマイズ](#カスタマイズ)
9. [トラブルシューティング](#トラブルシューティング)

---

## デモ構成

```
[UC Volume] CSVアップロード
  ↓
[ETL] Bronze → Silver → Gold（Lakeflow Declarative Pipelines）
  ↓
[Dashboard] 実験進捗ダッシュボード（AI/BI Dashboard）
  ↓
[ML] 物性値予測モデル（MLflow + Model Serving）
  ↓
[App] 研究者向け予測アプリ（Databricks App：FastAPI + React）
```

構築されるリソース:

| 種類 | 名前 | 説明 |
|------|------|------|
| Schema | `<catalog>.<schema>` | 全テーブル/モデル/Volumeの格納先 |
| Volume | `raw_data` | CSV生データの格納先 |
| Tables | `bronze_experiments`, `silver_experiments`, `gold_experiments` | メダリオンアーキテクチャ |
| Pipeline | `[dev] E2E_実験データパイプライン` | Lakeflow Declarative Pipelines |
| Model | `experiment_predictor` | Unity Catalog Model Registry |
| Serving Endpoint | `e2e-experiment-predictor` | Model Serving |
| Databricks App | `e2e-experiment-app` | FastAPI + React フロントエンド |
| Jobs | `E2E_初期化` / `E2E_ML学習` | セットアップ・ML学習ジョブ |

---

## 前提条件

### 必須

| 項目 | 要件 |
|------|------|
| Databricks ワークスペース | **Unity Catalog有効**、Serverless Compute有効 |
| 権限 | デプロイ先カタログに対する `CREATE SCHEMA`、`USE CATALOG`、`CREATE VOLUME`、`CREATE TABLE`、`CREATE MODEL` 権限 |
| Databricks CLI | v0.200 以上（`databricks -v` で確認） |
| Python | 3.12 以上 |
| uv | [Python packaging tool](https://docs.astral.sh/uv/) |

### 推奨リージョン・構成

- **Serverless Compute対応リージョン**（Pipeline / ML / Apps でサーバーレスを使用）
- **Serverless SQL Warehouse**（ダッシュボードのクエリ実行用）

### Databricks CLI プロファイルの準備

CLIの認証プロファイル（`~/.databrickscfg`）を事前に設定してください。

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile <your-profile>
```

設定後、以下で疎通確認:

```bash
databricks auth profiles | grep <your-profile>
databricks current-user me -p <your-profile>
```

---

## ディレクトリ構成

```
.
├── README.md
├── databricks.yml              # Databricks Asset Bundle 設定
├── pyproject.toml              # Python依存定義（ローカル開発用）
├── uv.lock
├── data/
│   └── sample_experiments.csv  # サンプル実験データ（10,000行）
├── scripts/
│   └── generate_data.py        # データ再生成用スクリプト
├── src/
│   └── sdp_pipeline.py         # Lakeflow Declarative Pipelines定義
├── notebooks/
│   ├── 00_setup.py             # スキーマ・Volume作成 + CSV配置確認
│   ├── 01_ml_training.py       # ML学習 + UC Model Registry登録
│   └── 02_model_serving.py     # Model Serving Endpoint作成
├── dashboards/
│   └── experiment_dashboard.lvdash.json  # AI/BI Dashboard 定義（手動import）
├── app/
│   ├── app.py                  # FastAPI バックエンド
│   ├── app.yaml                # Databricks App 実行設定
│   ├── pyproject.toml
│   └── frontend/               # React フロントエンド
└── resources/                  # Databricks Asset Bundle リソース定義
    ├── setup_job.yml           # 初期化ジョブ
    ├── pipeline.yml            # Lakeflow Declarative Pipelines
    ├── ml_job.yml              # ML学習+Servingデプロイ ジョブ
    └── app.yml                 # Databricks App
```

---

## サンプルデータ

`data/sample_experiments.csv` に10,000行のCSV（約520KB）を同梱しています。

| カラム | 型 | 説明 |
|--------|------|------|
| experiment_id | string | 実験ID（`EXP-00001` 形式） |
| experiment_date | date | 実験実施日 |
| material_a_ratio | double | 材料A配合比率（0.1〜0.9） |
| material_b_ratio | double | 材料B配合比率（= 1 - A） |
| temperature | int | 温度（℃）150〜250 |
| pressure | int | 圧力（MPa）30〜100 |
| tensile_strength | double | 引張強度 |
| elongation | double | 伸び率 |
| hardness | int | 硬度 |
| result_grade | string | 判定結果（A/B/C） |

データを再生成したい場合は `uv run scripts/generate_data.py` を実行してください。

---

## セットアップ手順

### 1. リポジトリ取得

```bash
git clone https://github.com/yyy4developer/e2e-data-platform-demo.git
cd e2e-data-platform-demo
```

### 2. Python環境

```bash
uv sync
```

### 3. デプロイ先の設定値を決める

以下の3つの値を、ご自身の環境に合わせて準備してください。本READMEでは以降 `<your-profile>` / `<your-catalog>` / `<your-schema>` と記載します。

| 変数 | 説明 | 例 |
|------|------|-----|
| `<your-profile>` | Databricks CLIプロファイル名 | `myworkspace` |
| `<your-catalog>` | デプロイ先Unity Catalogカタログ | `main` / `sandbox_yourname` |
| `<your-schema>` | スキーマ名 | `e2e_demo`（デフォルト） |

---

## デプロイ手順

Databricks Asset Bundle（DAB）でジョブ・パイプライン・アプリを一括デプロイします。

### 1. Bundleデプロイ（Jobs, Pipeline, App定義）

```bash
databricks bundle deploy -t dev \
  -p <your-profile> \
  --var="catalog=<your-catalog>"
```

**ポイント:**
- `catalog` はデフォルト値なしの必須変数です（各環境のカタログ名を必ず指定してください）
- `schema` のデフォルトは `e2e_demo`。変更する場合は `--var="schema=<your-schema>"` を追加
- `-t dev` で開発ターゲット（`bundle.target=dev`）としてデプロイされます

### 2. CSVをUC Volumeにアップロード + 初期化ジョブ実行

```bash
# UC Volumeへのパス作成とCSVアップロード
databricks fs mkdirs dbfs:/Volumes/<your-catalog>/<your-schema>/raw_data -p <your-profile>
databricks fs cp data/sample_experiments.csv \
  dbfs:/Volumes/<your-catalog>/<your-schema>/raw_data/sample_experiments.csv \
  -p <your-profile>

# 初期化ジョブ実行（スキーマ・Volume存在確認）
databricks bundle run setup_experiment_data -t dev -p <your-profile>
```

> **備考**: Notebookで手動実行する場合は、画面上部のウィジェットに `catalog` を必ず入力してください（デフォルト空）。

### 3. パイプライン実行（Bronze → Silver → Gold）

```bash
databricks bundle run experiment_pipeline -t dev -p <your-profile>
```

完了後、Unity Catalog Explorer で `<your-catalog>.<your-schema>.gold_experiments` が作成されていることを確認。

### 4. ML学習・Servingデプロイ

```bash
databricks bundle run ml_training -t dev -p <your-profile>
```

内部で以下を実行します:
1. `01_ml_training.py`: RandomForestRegressor（MultiOutput）で学習、MLflowで追跡、UC Model Registry に `experiment_predictor` として登録
2. `02_model_serving.py`: Serving Endpoint `e2e-experiment-predictor` を作成/更新（Scale-to-zero有効、Smallサイズ）

Endpoint準備完了まで数分かかります。

### 5. Databricks App デプロイ

```bash
# フロントエンドビルド（事前に一度だけ）
cd app/frontend
npm install && npm run build
cd ../..

# Appデプロイ
databricks bundle deploy -t dev -p <your-profile> --var="catalog=<your-catalog>"
databricks apps deploy e2e-experiment-app -p <your-profile>
```

デプロイ後、WorkspaceのApps画面から起動してアクセス可能です。

### 6. Dashboard インポート（手動）

Databricks AI/BI Dashboardは現状DAB経由で自動デプロイできないため、手動インポートします。

**事前置換（必須）:** `<CATALOG>` と `<SCHEMA>` プレースホルダーを自分の環境の値に置き換えます。

```bash
# 例: カタログ=main, スキーマ=e2e_demo の場合
sed -e 's/<CATALOG>/main/g' -e 's/<SCHEMA>/e2e_demo/g' \
  dashboards/experiment_dashboard.lvdash.json > /tmp/my_dashboard.lvdash.json
```

その後、Databricks UI で:
1. 左メニュー **「Dashboards」** → **「Create Dashboard」** → **「Import dashboard from file」**
2. `/tmp/my_dashboard.lvdash.json` を選択
3. Warehouse（Serverless SQL Warehouse推奨）を割り当てて保存

---

## 動作確認

### ETL完了チェック

```sql
-- Databricks SQL で以下を実行
SELECT COUNT(*) AS cnt FROM <your-catalog>.<your-schema>.gold_experiments;
-- 期待値: 10,000
```

### Model Serving テスト

```bash
databricks serving-endpoints query e2e-experiment-predictor -p <your-profile> \
  --json '{"dataframe_records":[{"material_a_ratio":0.7,"material_b_ratio":0.3,"temperature":190,"pressure":80,"ratio_interaction":0.21,"temp_pressure_interaction":15.2,"normalized_temperature":0.4,"normalized_pressure":0.714}]}'
```

`predictions` に3つの値（引張強度/伸び率/硬度）が返れば成功。

### Databricks App

1. Apps画面でステータスが `RUNNING` であることを確認
2. App URLにブラウザでアクセス
3. 「予測」タブで配合条件を入力し、物性値が返ることを確認
4. 「推薦」タブで目標物性値を入力し、Top-N推薦条件が表示されることを確認

---

## カスタマイズ

### スキーマ名を変更

```bash
databricks bundle deploy -t dev -p <your-profile> \
  --var="catalog=<your-catalog>" \
  --var="schema=<custom-schema-name>"
```

全リソース（Pipeline、ML学習、App）が自動的に新しいスキーマを参照します。

### Servingエンドポイント名を変更

`resources/app.yml`、`notebooks/02_model_serving.py`、`app/app.yaml` の `e2e-experiment-predictor` を置換してください。

### 追加ターゲット（staging/prod）

`databricks.yml` の `targets:` に `staging` / `prod` を追加し、それぞれ異なるカタログ/スキーマを指定できます。

```yaml
targets:
  dev:
    mode: development
    default: true
  prod:
    mode: production
    workspace:
      host: https://<your-prod-workspace>.cloud.databricks.com
```

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `bundle deploy` で `catalog` 変数エラー | 必須変数 `catalog` を指定していない | `--var="catalog=<your-catalog>"` を追加 |
| `Permission denied` on CREATE SCHEMA | カタログへの権限不足 | UCの `CREATE SCHEMA`、`USE CATALOG` 権限を付与 |
| Pipeline実行で Auto Loader エラー | CSVファイル未配置 | 初期化ジョブ（`setup_experiment_data`）と `databricks fs cp` を先に実行 |
| Model Serving Endpoint がREADYにならない | Scale-to-zeroからのコールドスタート | 初回起動は3〜5分程度かかります。Serving画面のログを確認 |
| Databricks App 起動時に401 | サービスプリンシパルの権限不足 | AppのService Principalに Serving Endpoint の `CAN_QUERY` 権限を付与（Bundle定義で自動付与されます） |
| Dashboard の表示エラー | `<CATALOG>.<SCHEMA>` の置換忘れ | `sed` コマンドで置換してから再import |

---

## ライセンス

デモ用途に自由にご利用ください。
