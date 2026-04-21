# Databricks notebook source
# MAGIC %md
# MAGIC # 実験データパイプライン（Lakeflow Declarative Pipelines）
# MAGIC
# MAGIC Bronze → Silver → Gold のメダリオンアーキテクチャで
# MAGIC 材料研究の実験データを段階的に加工する。
# MAGIC
# MAGIC ## 💡 デモポイント
# MAGIC - このパイプラインは **Lakeflow Designer** のGUI（ドラッグ&ドロップ）でも設計可能
# MAGIC - **Genie Code** で「CSVを取り込んでBronzeテーブルを作成して」と指示するだけでコード自動生成
# MAGIC - DE経験がほぼ0でも、これらのAI支援機能で構築可能

# COMMAND ----------

from pyspark import pipelines as dp
from pyspark.sql.functions import col, when, lit

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze: 生データ取り込み（Auto Loader）
# MAGIC
# MAGIC UC Volume上のCSVファイルをAuto Loaderで自動検知・取り込み。
# MAGIC スキーマ推論とスキーマ進化に自動対応。

# COMMAND ----------

@dp.table(
    name="bronze_experiments",
    comment="生データ: CSVから取り込んだ実験データ（未加工）",
    table_properties={"quality": "bronze"},
    schema="""
        experiment_id STRING COMMENT '実験の一意識別子 (EXP-00001形式)',
        experiment_date STRING COMMENT '実験実施日',
        material_a_ratio STRING COMMENT '材料Aの配合比率 (0.1〜0.9)',
        material_b_ratio STRING COMMENT '材料Bの配合比率 (= 1 - 材料A配合比)',
        temperature STRING COMMENT '実験温度 (℃)、範囲: 150〜250',
        pressure STRING COMMENT '実験圧力 (MPa)、範囲: 30〜100',
        tensile_strength STRING COMMENT '引張強度の測定値',
        elongation STRING COMMENT '伸び率の測定値',
        hardness STRING COMMENT '硬度の測定値',
        result_grade STRING COMMENT '判定結果 (A: 優良, B: 良, C: 不良)',
        _rescued_data STRING COMMENT 'Auto Loaderで救済されたデータ'
    """,
)
def bronze_experiments():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.inferColumnTypes", "false")
        .option("header", "true")
        .load(f"/Volumes/{spark.conf.get('pipeline.catalog')}/{spark.conf.get('pipeline.schema')}/raw_data/")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver: クレンジング + 型変換
# MAGIC
# MAGIC - データ型の明示的なキャスト
# MAGIC - NULL除去
# MAGIC - Expectations（データ品質ルール）で異常値をフィルタリング

# COMMAND ----------

@dp.table(
    name="silver_experiments",
    comment="クレンジング済み: 型変換・NULL除去・異常値フィルタリング済み",
    table_properties={"quality": "silver"},
    schema="""
        experiment_id STRING NOT NULL COMMENT '実験の一意識別子',
        experiment_date DATE NOT NULL COMMENT '実験実施日',
        material_a_ratio DOUBLE COMMENT '材料Aの配合比率 (0.1〜0.9)',
        material_b_ratio DOUBLE COMMENT '材料Bの配合比率 (= 1 - 材料A配合比)',
        temperature INT COMMENT '実験温度 (℃)、有効範囲: 100〜300',
        pressure INT COMMENT '実験圧力 (MPa)、有効範囲: 10〜200',
        tensile_strength DOUBLE COMMENT '引張強度の測定値 (> 0)',
        elongation DOUBLE COMMENT '伸び率の測定値',
        hardness INT COMMENT '硬度の測定値 (> 0)',
        result_grade STRING COMMENT '判定結果 (A: 優良, B: 良, C: 不良)'
    """,
)
@dp.expect_or_drop("valid_temperature", "temperature BETWEEN 100 AND 300")
@dp.expect_or_drop("valid_pressure", "pressure BETWEEN 10 AND 200")
@dp.expect_or_drop("valid_tensile_strength", "tensile_strength > 0")
@dp.expect_or_drop("valid_hardness", "hardness > 0")
@dp.expect("valid_grade", "result_grade IN ('A', 'B', 'C')")
def silver_experiments():
    return (
        dp.read_stream("bronze_experiments")
        .select(
            col("experiment_id").cast("string"),
            col("experiment_date").cast("date"),
            col("material_a_ratio").cast("double"),
            col("material_b_ratio").cast("double"),
            col("temperature").cast("int"),
            col("pressure").cast("int"),
            col("tensile_strength").cast("double"),
            col("elongation").cast("double"),
            col("hardness").cast("int"),
            col("result_grade").cast("string"),
        )
        .filter(col("experiment_id").isNotNull())
        .filter(col("experiment_date").isNotNull())
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold: 特徴量エンジニアリング
# MAGIC
# MAGIC ML学習用の特徴量を追加。配合比率の交互作用項、
# MAGIC 正規化された温度・圧力指標を算出。

# COMMAND ----------

@dp.table(
    name="gold_experiments",
    comment="分析・ML用: 特徴量エンジニアリング済み",
    table_properties={"quality": "gold"},
    schema="""
        experiment_id STRING NOT NULL COMMENT '実験の一意識別子',
        experiment_date DATE NOT NULL COMMENT '実験実施日',
        material_a_ratio DOUBLE COMMENT '材料Aの配合比率 (0.1〜0.9)',
        material_b_ratio DOUBLE COMMENT '材料Bの配合比率 (= 1 - 材料A配合比)',
        temperature INT COMMENT '実験温度 (℃)',
        pressure INT COMMENT '実験圧力 (MPa)',
        tensile_strength DOUBLE COMMENT '引張強度の測定値',
        elongation DOUBLE COMMENT '伸び率の測定値',
        hardness INT COMMENT '硬度の測定値',
        result_grade STRING COMMENT '判定結果 (A: 優良, B: 良, C: 不良)',
        ratio_interaction DOUBLE COMMENT '配合比の交互作用項 (A比 × B比)',
        temp_pressure_interaction DOUBLE COMMENT '温度×圧力の交互作用項 (温度*圧力/1000)',
        normalized_temperature DOUBLE COMMENT '正規化温度 ((温度-150)/100、0〜1スケール)',
        normalized_pressure DOUBLE COMMENT '正規化圧力 ((圧力-30)/70、0〜1スケール)',
        material_a_dominant BOOLEAN COMMENT '材料Aが主成分か (A配合比 > 0.5)'
    """,
)
def gold_experiments():
    return (
        dp.read_stream("silver_experiments")
        .withColumn("ratio_interaction", col("material_a_ratio") * col("material_b_ratio"))
        .withColumn("temp_pressure_interaction", col("temperature") * col("pressure") / 1000.0)
        .withColumn("normalized_temperature", (col("temperature") - 150) / 100.0)
        .withColumn("normalized_pressure", (col("pressure") - 30) / 70.0)
        .withColumn("material_a_dominant", when(col("material_a_ratio") > 0.5, lit(True)).otherwise(lit(False)))
    )
