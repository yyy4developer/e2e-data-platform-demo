# Databricks notebook source
# MAGIC %md
# MAGIC # Databricks Connect デモ: ローカル Compute vs クラウド Compute
# MAGIC
# MAGIC このノートブックは VSCode/Cursor + Databricks拡張機能 + `databricks-connect` 環境で
# MAGIC **どこでコードが実行されているか** を視覚的に示すデモです。
# MAGIC
# MAGIC ## 仕組み
# MAGIC
# MAGIC ```
# MAGIC [ローカル PC: .venv]                        [Databricks Cluster]
# MAGIC    │                                            │
# MAGIC    │  spark.table("foo")  ─── gRPC ──────────► │  ← 論理プランのみ送信
# MAGIC    │  df.filter(...)       ─── gRPC ──────────► │  ← lazy（即実行されない）
# MAGIC    │                                            │
# MAGIC    │  df.show() / .collect() / .toPandas()      │
# MAGIC    │  ──────────── action 実行 ──────────────►  │  ← クラスタで実プラン実行
# MAGIC    │  ◄────────── 結果ストリーム返却 ────────── │
# MAGIC    │                                            │
# MAGIC    │  pd.DataFrame として処理続行（local）        │
# MAGIC ```
# MAGIC
# MAGIC | 観点 | LOCAL（ローカルPC） | CLOUD（Databricks Cluster） |
# MAGIC |------|-------------------|---------------------------|
# MAGIC | 通常 Python / pandas / numpy | ✅ 実行 | - |
# MAGIC | ローカルファイル I/O（`open(...)`） | ✅ 実行 | - |
# MAGIC | Spark DataFrame transform | プラン構築のみ（lazy） | - |
# MAGIC | Spark Action（`.show/.collect/.toPandas/.count`） | 結果受け取り | ✅ プラン実行 |
# MAGIC | Spark 経由の I/O（UC Volume / DBFS / Delta） | - | ✅ 実行 |
# MAGIC | Python UDF | 定義のみ | ✅ executor 上で実行（serialized送信） |
# MAGIC | `SparkContext` / RDD API | ❌ 使用不可 | ❌ Connect 非対応 |
# MAGIC | `dbutils.fs/secrets/jobs/widgets` | 一部のみ | ✅ |
# MAGIC
# MAGIC ## 使い方
# MAGIC - VSCodeで `.py` ファイルを開き、各セル左の **「Run Cell」** ボタンで実行
# MAGIC - 出力ペインに `[LOCAL]` / `[CLOUD]` のラベルを付けて、どちらで実行されているか明示

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. セットアップ
# MAGIC
# MAGIC `DatabricksSession.builder.serverless()` で Serverless Compute に接続。

# COMMAND ----------

import os
import socket
import platform

from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.serverless().getOrCreate()
print("Connected. Spark version:", spark.version)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 「ローカル」での実行確認
# MAGIC
# MAGIC 通常の Python コード（pandas/numpy/標準ライブラリ）は **ローカルPCで実行** される。

# COMMAND ----------

print("===== [LOCAL] Pythonランタイム情報 =====")
print(f"Hostname:     {socket.gethostname()}")
print(f"Platform:     {platform.platform()}")
print(f"Python ver:   {platform.python_version()}")
print(f"CWD:          {os.getcwd()}")
print(f"USER:         {os.environ.get('USER')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 「クラウド」での実行確認
# MAGIC
# MAGIC Spark DataFrame の計算は **Databricksクラスタ（Serverless）で実行** される。
# MAGIC `spark.sql()` の結果として返ってきたメタ情報がクラウド側で取れる。

# COMMAND ----------

print("===== [CLOUD] Sparkクラスタ情報 =====")
cluster_info = spark.sql("""
  SELECT
    current_user()       AS spark_user,
    current_database()   AS current_db,
    current_catalog()    AS current_catalog,
    current_timestamp()  AS server_time,
    current_version()    AS spark_engine_version
""").collect()[0]

for k, v in cluster_info.asDict().items():
    print(f"  {k:25s}: {v}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ローカル と クラウド の役割分担
# MAGIC
# MAGIC `spark.read.table()` や `spark.sql()` で生成された DataFrame は遅延評価（lazy）。
# MAGIC `.show()` / `.collect()` / `.toPandas()` などの **action 操作で初めてクラスタ実行** される。
# MAGIC
# MAGIC 以下のセルでは、20,000行のデータをクラスタで集計し、ローカルにpandasとして引き戻す例。

# COMMAND ----------

# CATALOG/SCHEMA は実環境に合わせて変更
CATALOG = "demo_use_yao_catalog"
SCHEMA = "e2e_demo_schema"
TABLE = f"{CATALOG}.{SCHEMA}.gold_experiments"

# (1) [CLOUD] DataFrame構築 + 集計（クラスタで実行）
df = spark.table(TABLE)
agg = df.groupBy("result_grade").agg(
    {"tensile_strength": "avg", "elongation": "avg", "hardness": "avg", "*": "count"}
).orderBy("result_grade")

print("===== [CLOUD] スキーマと件数 =====")
df.printSchema()
print(f"Total rows: {df.count():,}  (← クラスタ側で集計)")

# COMMAND ----------

# (2) [CLOUD→LOCAL] 集計結果を pandas として取得
print("===== [CLOUD→LOCAL] 集計結果を pandas に変換 =====")
pandas_df = agg.toPandas()  # ← ここでクラスタ実行 + データがローカルへ転送
print(pandas_df)
print(f"\ntype: {type(pandas_df).__module__}.{type(pandas_df).__name__}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. 性能比較: ローカル処理 vs クラウド処理
# MAGIC
# MAGIC **20,000行 → そのままローカルに `.toPandas()` で引き、ローカルで集計** vs
# MAGIC **クラウド側で集計してから少量だけローカルに引く**。

# COMMAND ----------

import time

# (A) [LOCAL重視] 全データをローカルにpullしてからpandasで集計
t0 = time.time()
all_local = spark.table(TABLE).toPandas()
result_a = all_local.groupby("result_grade").agg(
    cnt=("experiment_id", "count"),
    avg_tensile=("tensile_strength", "mean"),
)
t_local = time.time() - t0
print(f"[A: 全件ローカル集計] {t_local:.2f}s, ローカルメモリ: {len(all_local):,}行")
print(result_a)

# COMMAND ----------

# (B) [CLOUD重視] クラスタ側で集計、結果のみローカルに引く
t0 = time.time()
result_b = (spark.table(TABLE)
            .groupBy("result_grade")
            .agg({"experiment_id": "count", "tensile_strength": "avg"})
            .toPandas())
t_cloud = time.time() - t0
print(f"[B: クラスタ集計→結果のみ取得] {t_cloud:.2f}s, ローカルメモリ: {len(result_b):,}行")
print(result_b)

# COMMAND ----------

print("===== まとめ =====")
print(f"[A] 全件ローカル集計:    {t_local:.2f}s")
print(f"[B] クラスタ集計のみ:    {t_cloud:.2f}s")
print()
print("→ データが大きくなるほど (B) の差が顕著。")
print("→ Spark DataFrame は『なるべくクラウド側で集計してから .toPandas()』が鉄則。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. 確認ポイント
# MAGIC
# MAGIC | 観点 | LOCAL（ローカルPC） | CLOUD（Databricks Cluster） |
# MAGIC |------|-------------------|---------------------------|
# MAGIC | hostname | 自分のMac/PC名 | （直接見えない、cluster_id等で識別） |
# MAGIC | Python版 | venv の `.python-version` | クラスタ runtime の Python |
# MAGIC | numpy/pandas | ローカル.venvのバージョン | クラスタ DBR のバージョン |
# MAGIC | Spark DataFrame | gRPC越しに命令 | 実際の計算実行 |
# MAGIC | UC テーブル/Volume I/O | 不可 | 可 |
# MAGIC | 一部のSpark機能 (.toPandas等) | 結果を引っ張る側 | 結果を生成する側 |
# MAGIC
# MAGIC ## ヒント
# MAGIC - **エラー: `ConnectError`** → `.databricks/.databricks.env` の `DATABRICKS_*` 変数が拡張機能経由でセットされているか確認
# MAGIC - **エラー: `Unsupported Python version`** → DBR 15 系は Python 3.11、DBR 16+ は 3.12 を venv に指定
# MAGIC - **拡張機能の Configuration を確認**: `Auth Type: Profile 'fevm-demo-use-yao'` / `Serverless` と表示されていれば OK
