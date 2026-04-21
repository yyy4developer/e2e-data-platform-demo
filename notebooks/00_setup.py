# Databricks notebook source
# MAGIC %md
# MAGIC # 初期化: Schema・Volume作成 + サンプルデータアップロード
# MAGIC
# MAGIC 本デモの初期セットアップ。
# MAGIC - Unity Catalog スキーマの作成
# MAGIC - UC Volume の作成（生データ格納用）
# MAGIC - サンプル実験データ（CSV）のアップロード

# COMMAND ----------

dbutils.widgets.text("catalog", "", "カタログ名（必須）")
dbutils.widgets.text("schema", "e2e_demo", "スキーマ名")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"カタログ: {catalog}")
print(f"スキーマ: {schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. スキーマ作成

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
print(f"スキーマ {catalog}.{schema} を作成しました")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. UC Volume 作成（生データ格納用）

# COMMAND ----------

spark.sql(f"""
    CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.raw_data
    COMMENT '実験データの生データ格納用ボリューム'
""")
print(f"ボリューム {catalog}.{schema}.raw_data を作成しました")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. サンプルCSVのアップロード確認
# MAGIC
# MAGIC CSVはDABデプロイ後に `databricks fs cp` コマンドで別途アップロード済み。
# MAGIC ここではアップロード結果の確認のみ行う。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. 確認

# COMMAND ----------

files = dbutils.fs.ls(f"/Volumes/{catalog}/{schema}/raw_data/")
for f in files:
    print(f"  {f.name} ({f.size:,} bytes)")

# COMMAND ----------

volume_path = f"/Volumes/{catalog}/{schema}/raw_data/sample_experiments.csv"
df = spark.read.option("header", "true").csv(volume_path)
print(f"行数: {df.count():,}")
df.show(5)
