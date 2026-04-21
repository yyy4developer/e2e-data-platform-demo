# E2E データ基盤デモ on Databricks

材料研究の実験データを題材に、Databricksで **ETL → 分析 → ML → App** が一つの基盤で完結することを示すデモ環境です。UI中心のハンズオンを想定しています。

## 目次

1. [デモ構成](#デモ構成)
2. [前提条件](#前提条件)
3. [ディレクトリ構成](#ディレクトリ構成)
4. [サンプルデータ](#サンプルデータ)
5. [ハンズオン手順（UI中心）](#ハンズオン手順ui中心)
6. [動作確認](#動作確認)
7. [カスタマイズ](#カスタマイズ)
8. [トラブルシューティング](#トラブルシューティング)

---

## デモ構成

```
[UC Volume] CSVアップロード（UI）
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

| 種類 | 名前 | 作成方法 |
|------|------|----------|
| Catalog | `<your-catalog>` | **UI（手動）** |
| Schema | `<your-catalog>.<your-schema>` | **UI（手動）** |
| Volume | `raw_data` | **UI（手動）** |
| Tables | `bronze_experiments`, `silver_experiments`, `gold_experiments` | Pipeline実行時に自動作成 |
| Pipeline | `[dev] E2E_実験データパイプライン` | DAB デプロイ |
| Trigger Job | `[dev] E2E_ファイル到着トリガー` | DAB デプロイ（Volume新規ファイルでPipeline自動起動） |
| Model | `experiment_predictor` | ML Job実行時に自動登録 |
| Serving Endpoint | `e2e-experiment-predictor` | ML Job内で自動作成 |
| Databricks App | `e2e-experiment-app` | DAB デプロイ |
| Job | `E2E_ML学習` | DAB デプロイ |
| Dashboard | 実験進捗ダッシュボード | **UI（手動import）** |

---

## 前提条件

### 必須

| 項目 | 要件 |
|------|------|
| Databricks ワークスペース | **Unity Catalog有効**、Serverless Compute有効 |
| 権限 | カタログに対する `CREATE SCHEMA`、`CREATE VOLUME`、`CREATE TABLE`、`CREATE MODEL`、`USE CATALOG` 権限 |
| Databricks CLI | v0.200 以上（`databricks -v` で確認） |
| Python | 3.12 以上 |
| uv | [Python packaging tool](https://docs.astral.sh/uv/) |

### 推奨構成

- **Serverless Compute対応リージョン**（Pipeline / ML / Apps でサーバーレスを使用）
- **Serverless SQL Warehouse**（ダッシュボードのクエリ実行用）

### Databricks CLI プロファイル設定

```bash
databricks auth login \
  --host https://<your-workspace>.cloud.databricks.com \
  --profile <your-profile>
```

疎通確認:

```bash
databricks current-user me -p <your-profile>
```

---

## ディレクトリ構成

```
.
├── README.md
├── databricks.yml              # Databricks Asset Bundle 設定
├── pyproject.toml              # Python依存定義
├── uv.lock
├── data/
│   └── sample_experiments.csv  # サンプル実験データ（10,000行）※ UI でVolumeにアップロード
├── scripts/
│   └── generate_data.py        # データ再生成用スクリプト
├── src/
│   └── sdp_pipeline.py         # Lakeflow Declarative Pipelines定義
├── notebooks/
│   ├── 01_ml_training.py       # ML学習 + UC Model Registry登録
│   └── 02_model_serving.py     # Model Serving Endpoint作成
├── dashboards/
│   └── experiment_dashboard.lvdash.json  # AI/BI Dashboard 定義（UI でインポート）
├── app/                        # Databricks App（FastAPI + React）
└── resources/                  # DAB リソース定義
    ├── pipeline.yml            # Lakeflow Declarative Pipelines
    ├── pipeline_trigger.yml    # ファイル到着でPipeline自動起動するジョブ
    ├── ml_job.yml              # ML学習+Servingデプロイ ジョブ
    └── app.yml                 # Databricks App
```

---

## サンプルデータ

`data/sample_experiments.csv` に10,000行のCSV（約520KB）を同梱しています。ハンズオン中にUI経由でVolumeへアップロードします。

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

## ハンズオン手順（UI中心）

Databricks UIの操作感を体験しながら構築していきます。以降の手順では以下の値を使います。

| 変数 | 例 |
|------|----|
| `<your-catalog>` | `main` / `sandbox_yourname` など（UI で事前作成） |
| `<your-schema>` | `e2e_demo`（推奨） |
| `<your-profile>` | Databricks CLI プロファイル名 |

### Step 1. Catalog の作成（UI）

> カタログが既にある場合はスキップ。

1. 左サイドバー **「Catalog」** → ページ右上 **「Create catalog」**
2. **Type**: `Standard`、**Name**: `<your-catalog>` を入力
3. **Storage location** を指定（外部ロケーション or managed storage）
4. **「Create」** → 完了

### Step 2. Schema の作成（UI）

1. Catalog Explorer で `<your-catalog>` を開く
2. 右上 **「Create」** → **「Schema」**
3. **Name**: `<your-schema>`（例: `e2e_demo`）を入力 → **「Create」**

### Step 3. Volume の作成（UI）

1. 作成した Schema を開く
2. 右上 **「Create」** → **「Volume」**
3. **Name**: `raw_data`、**Type**: `Managed volume` → **「Create」**

### Step 4. サンプルCSVをVolumeにアップロード（UI）

1. `raw_data` Volume を開く
2. 右上 **「Upload to this volume」** をクリック
3. ローカルの `data/sample_experiments.csv` を選択 → アップロード
4. アップロード後、ファイルが表示されていることを確認

### Step 5. リポジトリの取得 & 依存インストール（ローカル）

```bash
git clone https://github.com/yyy4developer/e2e-data-platform-demo.git
cd e2e-data-platform-demo
uv sync
```

### Step 6. DAB デプロイ（CLI）

Step 1〜3で作成したカタログ・スキーマ名を変数として渡してデプロイします。

```bash
databricks bundle deploy -t dev \
  -p <your-profile> \
  --var="catalog=<your-catalog>" \
  --var="schema=<your-schema>"
```

デプロイされるリソース:
- Lakeflow Declarative Pipelines（`E2E_実験データパイプライン`）
- ファイル到着トリガージョブ（`E2E_ファイル到着トリガー`）※ Volume にCSVが追加されるとPipelineを自動起動
- ML学習ジョブ（`E2E_ML学習`）
- Databricks App（`e2e-experiment-app`）

### Step 7. Pipeline 実行（ファイル到着で自動起動）

Step 4 でCSVを Volume にアップロードすると、**ファイル到着トリガージョブ** (`E2E_ファイル到着トリガー`) が自動で検知し、Pipeline を起動します（最短1分以内）。

UI で動きを確認:
1. 左サイドバー **「Jobs & Pipelines」** → **「Jobs」** タブ
2. `[dev ...] E2E_ファイル到着トリガー` を開く → 自動的に Run が開始されているのを確認
3. 続けて **「Pipelines」** タブ → `[dev ...] E2E_実験データパイプライン` → Bronze → Silver → Gold の順に完了するのを画面で確認

完了後、Catalog Explorer で `<your-catalog>.<your-schema>.gold_experiments` が作成されていることを確認してください。

> **手動実行したい場合**: Pipelines 画面で該当パイプラインを開き、右上の **「Start」** から起動可能です。

### Step 8. Dashboard のインポート（UI）

ダッシュボード定義ファイル内のプレースホルダーを実際の値に置換してからインポートします。

```bash
# ローカルで置換（例: main.e2e_demo）
sed -e 's/<CATALOG>/<your-catalog>/g' -e 's/<SCHEMA>/<your-schema>/g' \
  dashboards/experiment_dashboard.lvdash.json > /tmp/my_dashboard.lvdash.json
```

UI で:
1. 左サイドバー **「Dashboards」** → 右上 **「Create dashboard」** → **「Import dashboard from file」**
2. `/tmp/my_dashboard.lvdash.json` を選択
3. 画面右上の **「Choose a warehouse」** で **Serverless SQL Warehouse** を選択
4. 各ビジュアルにデータが表示されることを確認

### Step 9. ML学習ジョブ実行（UI）

1. 左サイドバー **「Jobs & Pipelines」** → **「Jobs」** タブ
2. `[dev ...] E2E_ML学習` をクリック
3. 右上 **「Run now」** をクリック
4. 2タスク（`train_and_register` → `deploy_serving`）が順に完了するのを確認

完了後、以下を UI で確認できます:
- **Catalog Explorer**: `<catalog>.<schema>.experiment_predictor` モデルが登録されている
- **Serving**: エンドポイント `e2e-experiment-predictor` が作成されている（READY まで3〜5分）

### Step 10. Databricks App の起動・アクセス（UI）

1. 左サイドバー **「Compute」** → **「Apps」** タブ
2. `e2e-experiment-app` をクリック
3. ステータスが `RUNNING` であることを確認（起動まで数分）
4. App URL にアクセス → 「予測」タブ、「推薦」タブを操作

---

## 動作確認

### ETL完了チェック（SQL Editor）

```sql
SELECT COUNT(*) AS cnt FROM <your-catalog>.<your-schema>.gold_experiments;
-- 期待値: 10,000
```

### Model Serving テスト

Serving画面の **「Query endpoint」** パネルで以下を貼り付けて実行:

```json
{
  "dataframe_records": [
    {
      "material_a_ratio": 0.7, "material_b_ratio": 0.3,
      "temperature": 190, "pressure": 80,
      "ratio_interaction": 0.21, "temp_pressure_interaction": 15.2,
      "normalized_temperature": 0.4, "normalized_pressure": 0.714
    }
  ]
}
```

`predictions` に3つの値（引張強度/伸び率/硬度）が返れば成功。

---

## カスタマイズ

### スキーマ名を変更

Step 2 で作成するスキーマ名を変えた場合、Step 6 の `--var="schema=..."` に同じ値を指定してください。

### App/Endpoint名を変更

`resources/app.yml`、`notebooks/02_model_serving.py`、`app/app.yaml` 内の `e2e-experiment-predictor` / `e2e-experiment-app` を置換してください。

### 追加ターゲット（staging/prod）

`databricks.yml` の `targets:` に `staging` / `prod` を追加し、それぞれ異なるカタログ/スキーマを指定できます。

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `bundle deploy` で `catalog` 変数エラー | 必須変数 `catalog` を指定していない | `--var="catalog=<your-catalog>"` を追加 |
| `Permission denied` on CREATE SCHEMA | カタログへの権限不足 | UCの `CREATE SCHEMA`、`USE CATALOG` 権限を付与 |
| Pipeline実行で Auto Loader エラー | CSVファイル未配置、または Volume パスの catalog/schema 不一致 | Step 4 の CSVアップロード先を確認 |
| Model Serving Endpoint がREADYにならない | Scale-to-zeroからのコールドスタート | 初回起動は3〜5分。Serving画面のログを確認 |
| Databricks App 起動時に401 | サービスプリンシパルの Endpoint 権限不足 | AppのService Principalに Serving Endpoint の `CAN_QUERY` 権限を付与（Bundle定義で自動付与されます） |
| Dashboard の表示エラー | `<CATALOG>.<SCHEMA>` の置換忘れ | Step 8 の sed コマンドで置換してから再インポート |

---

## ライセンス

デモ用途に自由にご利用ください。
