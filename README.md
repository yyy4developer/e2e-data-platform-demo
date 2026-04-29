# E2E データ基盤デモ on Databricks

材料研究の実験データを題材に、Databricksで **ETL → 分析 → ML → App** が一つの基盤で完結することを示すデモ環境です。UI中心のハンズオンを想定しています。

## 目次

1. [デモ構成](#デモ構成)
2. [前提条件](#前提条件)
3. [ディレクトリ構成](#ディレクトリ構成)
4. [サンプルデータ](#サンプルデータ)
5. [ハンズオン手順（UI中心）](#ハンズオン手順ui中心)
6. [動作確認](#動作確認)
7. [VS Code (Cursor) Databricks 拡張機能](#vs-code-cursor-databricks-拡張機能)
8. [カスタマイズ](#カスタマイズ)
9. [トラブルシューティング](#トラブルシューティング)

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
| Databricks App | `e2e-experiment-app` | **UI 作成（推奨）** または DAB 再デプロイ |
| Job | `E2E_ML学習` | DAB デプロイ |
| Dashboard | `E2E_実験データ分析ダッシュボード` | DAB デプロイ（テンプレ → sed レンダー → 自動デプロイ） |

---

## 前提条件

### 必須

| 項目 | 要件 |
|------|------|
| Databricks ワークスペース | **Unity Catalog有効**、Serverless Compute有効 |
| 権限 | カタログに対する `CREATE SCHEMA`、`CREATE VOLUME`、`CREATE TABLE`、`CREATE MODEL`、`USE CATALOG` 権限 |
| Databricks CLI | v0.200 以上（`databricks -v` で確認） |
| Python | 3.11 以上（ローカル開発用。Databricks側クラスタとは独立） |
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
│   └── experiment_dashboard.lvdash.json  # AI/BI Dashboard 定義（unqualified テーブル名、DABデプロイ時にcatalog/schema自動補完）
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

### Step 4. Volume が空であることを確認

`raw_data` Volume を開き、ファイルが何も入っていないことを確認してください。

> **CSVは Step 7 でアップロードします**。ファイル到着トリガーは **アクティブになった後** に到着したファイルのみを検知するため、DABデプロイ（Step 6）より前にアップロードすると自動実行されません。

### Step 5. リポジトリの取得 & 依存インストール（ローカル）

```bash
git clone https://github.com/yyy4developer/e2e-data-platform-demo.git
cd e2e-data-platform-demo
uv sync
```

> React フロントエンドの **ビルド成果物 `app/frontend/dist/` はリポジトリに同梱済み**のため、Node.js は不要です。
> フロントエンドに変更を加える場合のみ、`cd app/frontend && npm install && npm run build` で再生成してください。

### Step 6. DAB デプロイ（CLI）

**6-1. Warehouse ID を取得**

Databricks UI で **「SQL Warehouses」** → 利用する Serverless Warehouse を開き、**「Endpoint details」** タブで ID（`XXXXXXXX` 形式）をコピー。

**6-2. DAB デプロイ**

```bash
databricks bundle deploy -t dev \
  -p <your-profile> \
  --var="catalog=<your-catalog>" \
  --var="schema=<your-schema>" \
  --var="warehouse_id=<your-warehouse-id>"
```

デプロイされるリソース:
- Lakeflow Declarative Pipelines（`E2E_実験データパイプライン`）
- ファイル到着トリガージョブ（`E2E_ファイル到着トリガー`）※ Volume にCSVが追加されるとPipelineを自動起動
- ML学習ジョブ（`E2E_ML学習`）
- AI/BI Dashboard（`E2E_実験データ分析ダッシュボード`） ※ dataset_catalog/dataset_schema により各クエリのテーブル参照が自動解決

> **注**: Databricks App（`e2e-experiment-app`）は Serving Endpoint 依存のため、この段階ではデプロイしません（Step 9 で作成）。
> リポジトリ内の `app/` 配下のファイルは bundle sync で workspace にアップロードされます（Step 9 の source として利用）。

### Step 7. CSVアップロード → Pipeline 自動実行（UI）

**7-1. CSVを Volume にアップロード**

1. Catalog Explorer で `raw_data` Volume を開く
2. 右上 **「Upload to this volume」** をクリック
3. ローカルの `data/sample_experiments.csv` を選択 → アップロード
4. アップロード後、ファイルが表示されていることを確認

**7-2. ファイル到着トリガーが自動検知 → Pipeline を起動**

`E2E_ファイル到着トリガー` ジョブが最終変更から約90秒待った後、Pipeline を自動起動します。

UI で動きを確認:
1. 左サイドバー **「Jobs & Pipelines」** → **「Jobs」** タブ
2. `[dev ...] E2E_ファイル到着トリガー` を開く → 自動的に Run が開始されているのを確認（アップロードから約1〜2分）
3. 続けて **「Pipelines」** タブ → `[dev ...] E2E_実験データパイプライン` → Bronze → Silver → Gold の順に完了するのを画面で確認

完了後、Catalog Explorer で `<your-catalog>.<your-schema>.gold_experiments` が作成されていることを確認してください。

> **手動実行したい場合**: Pipelines 画面で該当パイプラインを開き、右上の **「Start」** から起動可能です。

### Step 8. ML学習ジョブ実行（UI）

1. 左サイドバー **「Jobs & Pipelines」** → **「Jobs」** タブ
2. `[dev ...] E2E_ML学習` をクリック
3. 右上 **「Run now」** をクリック
4. 2タスク（`train_and_register` → `deploy_serving`）が順に完了するのを確認

完了後、以下を UI で確認できます:
- **Catalog Explorer**: `<catalog>.<schema>.experiment_predictor` モデルが登録されている
- **Serving**: エンドポイント `e2e-experiment-predictor` が作成されている（READY まで3〜5分）

### Step 9. Databricks App の作成・起動

Step 9 で Serving Endpoint (`e2e-experiment-predictor`) が作成された後、App をデプロイします。**以下のいずれかの方法**を選択してください。

#### Option A: UI で作成（ハンズオン推奨）

1. 左サイドバー **「Compute」** → **「Apps」** → 右上 **「Create app」**
2. **「Custom app」** を選択
3. 以下を入力:

   | 項目 | 値 |
   |------|----|
   | App name | `e2e-experiment-app` |
   | Description | `材料実験条件の予測・推薦アプリ` |

4. **「Advanced settings」** を展開し、**「Add resource」** で Serving Endpoint を紐付け:

   | 項目 | 値 |
   |------|----|
   | Resource type | `Serving endpoint` |
   | Serving endpoint | `e2e-experiment-predictor` |
   | Permission | `CAN_QUERY` |
   | Resource name | `serving-endpoint` |

5. **「Create app」** をクリック → 空の App が作成される
6. App 画面 → **「Deploy」** → **「Choose source code」** で以下を指定:
   - Source: **Workspace files**
   - Path: `/Workspace/Users/<your-user>/.bundle/e2e_data_platform_demo/dev/files/app`
     （※ Step 6 の `bundle deploy` 実行ログに表示された `Workspace:` のパス配下 `app/` を指定）
7. **「Deploy」** をクリック → ビルド・起動まで数分

#### Option B: DAB 経由で再デプロイ（CI/CD向け）

Serving Endpoint が作成済みなので、`app.yml.disabled` を有効化して再デプロイします。

```bash
# App 定義を有効化
mv resources/app.yml.disabled resources/app.yml

# 再デプロイ
databricks bundle deploy -t dev \
  -p <your-profile> \
  --var="catalog=<your-catalog>" \
  --var="schema=<your-schema>"
```

#### 共通: 動作確認

1. 左サイドバー **「Compute」** → **「Apps」** タブ
2. `e2e-experiment-app` のステータスが **`RUNNING`** であることを確認（起動まで数分）
3. App URL にアクセス → 「予測」タブ、「推薦」タブを操作

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

## VS Code (Cursor) Databricks 拡張機能

[Databricks 拡張機能](https://marketplace.visualstudio.com/items?itemName=databricks.databricks) を使うと、ローカルの IDE から Databricks ワークスペースへ直接接続して開発できます。

### 拡張機能でできること

| カテゴリ | 機能 |
|---------|------|
| **接続管理** | プロファイル / クラスタ / Serverless / 環境（dev/prod） の切替 |
| **Notebook 実行** | `.py` / `.ipynb` のセル単位実行・デバッグ（Run Cell / Debug Cell） |
| **Run on Databricks** | ローカルファイルをクラスタ実行 / Job として実行 |
| **Databricks Connect** | ローカルから Spark セッションを開き、リモートクラスタで処理を実行 |
| **Bundle 連携** | DAB リソース一覧表示、ターゲット切替、`bundle deploy/run` の UI 操作 |
| **ワークスペース同期** | ローカルファイルをワークスペース配下にミラーリング |
| **Python 環境連携** | venv/conda + `databricks-connect` の自動セットアップ補助 |

### 拡張機能でできないこと（2026/4 時点）

- **Catalog Explorer 相当のテーブル/Volume ブラウズ機能は未実装**
  - コミュニティリクエスト段階（[DECO-26583](https://databricks.atlassian.net/browse/DECO-26583)）
  - 代替: AI Dev Kit MCP (`execute_sql` / `manage_uc_objects` / `manage_volume_files`) で自然言語ベースの操作
- Volume ファイルの IDE 内プレビューは限定的

### Databricks Connect の仕組み

`databricks-connect` は **Spark Connect (gRPC)** を介してローカル Python プロセスからリモート Databricks クラスタへ接続するライブラリです。

```
[ローカル PC: .venv]                         [Databricks Cluster]
   │                                              │
   │  spark.table("foo")  ─── gRPC ──────────►  │  ← 論理プランのみ送信
   │  df.filter(...)       ─── gRPC ──────────►  │  ← lazy（即時実行されない）
   │                                              │
   │  df.show() / .toPandas()                    │
   │  ──────────── action 実行 ──────────────►   │  ← クラスタで実プラン実行
   │  ◄──────── 結果ストリーム返却 ──────────── │
   │                                              │
   │  pd.DataFrame として処理続行（local）         │
```

| 観点 | LOCAL（ローカルPC） | CLOUD（Databricks Cluster） |
|------|-------------------|---------------------------|
| 通常 Python / pandas / numpy | ✅ 実行 | - |
| ローカルファイル I/O（`open(...)`） | ✅ 実行 | - |
| Spark DataFrame transform | プラン構築のみ（lazy） | - |
| Spark Action（`.show/.collect/.toPandas/.count`） | 結果受け取り | ✅ プラン実行 |
| Spark 経由の I/O（UC Volume / DBFS / Delta） | - | ✅ 実行 |
| Python UDF | 定義のみ | ✅ executor で実行 |
| `SparkContext` / RDD API | ❌ Connect 非対応 | ❌ Connect 非対応 |
| `dbutils.fs/secrets/jobs/widgets` | 一部のみ | ✅ |

### バージョンの整合（重要）

`databricks-connect` のメジャーバージョンを **Databricks Runtime (DBR) と一致** させてください:

| 接続先 | Python | databricks-connect |
|--------|--------|-------------------|
| Serverless（推奨） | 3.11 / 3.12 | latest（自動互換） |
| DBR 13/14 | 3.10 | `>=13,<14` 系 |
| **DBR 15** | **3.11** | **`>=15,<16`** 系 |
| DBR 16+ | 3.12 | `>=16` 系 |

> 本リポジトリは `pyproject.toml` で `databricks-connect>=15,<16` を pin（DBR 15 / Serverless 互換）。

### セットアップ手順

1. **拡張機能インストール**: VS Code / Cursor のマーケットプレイスから「Databricks」を検索してインストール
2. **プロジェクトを開く**: 本リポジトリをワークスペースとして開く
3. **左サイドバー の Databricks アイコン** → 認証ホスト・プロファイル選択
4. **`databricks-connect` インストール**: パネル下部の「Install databricks-connect」をクリック → venv に自動インストール（または `uv sync` で本リポジトリの定義から取得）
5. **Compute 選択**: Serverless / 既存クラスタ / 新規クラスタ から選択

### ハンズオン用デモ Notebook

[`notebooks/03_databricks_connect_demo.py`](notebooks/03_databricks_connect_demo.py) を VS Code / Cursor で開き、各セルの **「Run Cell」** で実行してください。

- ローカルとクラウドの実行場所を `[LOCAL]` / `[CLOUD]` で明示
- Spark DataFrame の lazy 評価を体験
- 全件ローカル集計 vs クラスタ集計の性能差を比較

### ローカル個人設定（dev target の host）

DAB の `dev` target にホストを書かない構成にしているため、個人ローカル環境では `databricks.local.yml` に host を書いて拡張機能に解決させる運用です（このファイルは git 管理外）。

```yaml
# databricks.local.yml (gitignored)
targets:
  dev:
    workspace:
      host: https://<your-workspace>.cloud.databricks.com
```

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
| Dashboard の表示エラー | `dataset_catalog` / `dataset_schema` の指定漏れ | `bundle deploy` 時に `--var="catalog=..." --var="schema=..." --var="warehouse_id=..."` を全て指定 |

---

## ライセンス

デモ用途に自由にご利用ください。
