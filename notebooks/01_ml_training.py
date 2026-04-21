# Databricks notebook source
# MAGIC %md
# MAGIC # ML学習: 実験条件から物性値を予測
# MAGIC
# MAGIC Goldテーブルのデータを使って、配合条件から物性値を予測するモデルを学習する。
# MAGIC - 特徴量: material_a_ratio, material_b_ratio, temperature, pressure, ratio_interaction, temp_pressure_interaction
# MAGIC - ターゲット: tensile_strength, elongation, hardness
# MAGIC - モデル: RandomForestRegressor (MultiOutput)
# MAGIC - MLflowで実験追跡・モデル登録

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_use_yao_catalog", "カタログ名")
dbutils.widgets.text("schema", "km_e2e_demo", "スキーマ名")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. データ読み込み

# COMMAND ----------

import pandas as pd

gold_df = spark.table(f"{catalog}.{schema}.gold_experiments").toPandas()
print(f"データ件数: {len(gold_df):,}")
gold_df.head()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 特徴量とターゲットの準備

# COMMAND ----------

FEATURE_COLS = [
    "material_a_ratio",
    "material_b_ratio",
    "temperature",
    "pressure",
    "ratio_interaction",
    "temp_pressure_interaction",
    "normalized_temperature",
    "normalized_pressure",
]

TARGET_COLS = [
    "tensile_strength",
    "elongation",
    "hardness",
]

X = gold_df[FEATURE_COLS]
y = gold_df[TARGET_COLS]

print(f"特徴量: {X.shape}")
print(f"ターゲット: {y.shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 学習・評価（MLflow追跡）

# COMMAND ----------

import mlflow
from sklearn.ensemble import RandomForestRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import numpy as np

# MLflow実験設定
experiment_name = f"/Users/yunyi.yao@databricks.com/km_experiment_prediction"
mlflow.set_experiment(experiment_name)

# データ分割
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print(f"学習データ: {len(X_train):,}")
print(f"テストデータ: {len(X_test):,}")

# COMMAND ----------

with mlflow.start_run(run_name="random_forest_multi_output") as run:
    # ハイパーパラメータ
    params = {
        "n_estimators": 200,
        "max_depth": 12,
        "min_samples_split": 5,
        "min_samples_leaf": 2,
        "random_state": 42,
    }
    mlflow.log_params(params)
    mlflow.log_param("feature_columns", FEATURE_COLS)
    mlflow.log_param("target_columns", TARGET_COLS)

    # モデル学習
    base_model = RandomForestRegressor(**params)
    model = MultiOutputRegressor(base_model)
    model.fit(X_train, y_train)

    # 予測
    y_pred = model.predict(X_test)

    # 評価指標（各ターゲットごと）
    for i, target in enumerate(TARGET_COLS):
        rmse = np.sqrt(mean_squared_error(y_test.iloc[:, i], y_pred[:, i]))
        mae = mean_absolute_error(y_test.iloc[:, i], y_pred[:, i])
        r2 = r2_score(y_test.iloc[:, i], y_pred[:, i])

        mlflow.log_metric(f"{target}_rmse", round(rmse, 4))
        mlflow.log_metric(f"{target}_mae", round(mae, 4))
        mlflow.log_metric(f"{target}_r2", round(r2, 4))

        print(f"{target}: RMSE={rmse:.4f}, MAE={mae:.4f}, R2={r2:.4f}")

    # モデル登録
    model_name = f"{catalog}.{schema}.experiment_predictor"
    mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        registered_model_name=model_name,
        input_example=X_train.head(5),
    )

    print(f"\nモデル登録完了: {model_name}")
    print(f"Run ID: {run.info.run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. 推薦ロジックのテスト
# MAGIC
# MAGIC 目標物性値に最も近い配合条件を探索する。

# COMMAND ----------

import itertools

def recommend_conditions(model, target_props, n_top=5):
    """目標物性値に近い配合条件をグリッドサーチで推薦する。

    Args:
        model: 学習済みMultiOutputRegressor
        target_props: dict {"tensile_strength": 50, "elongation": 15, "hardness": 80}
        n_top: 返す候補数
    """
    # 探索グリッド
    a_ratios = np.arange(0.1, 0.91, 0.05)
    temps = np.arange(150, 251, 5)
    pressures = np.arange(30, 101, 5)

    candidates = []
    for a, t, p in itertools.product(a_ratios, temps, pressures):
        b = round(1.0 - a, 2)
        candidates.append({
            "material_a_ratio": round(a, 2),
            "material_b_ratio": b,
            "temperature": int(t),
            "pressure": int(p),
            "ratio_interaction": round(a * b, 4),
            "temp_pressure_interaction": round(t * p / 1000, 4),
            "normalized_temperature": round((t - 150) / 100, 4),
            "normalized_pressure": round((p - 30) / 70, 4),
        })

    cand_df = pd.DataFrame(candidates)
    preds = model.predict(cand_df[FEATURE_COLS])

    # 目標との距離計算（正規化）
    target_arr = np.array([target_props.get(t, 0) for t in TARGET_COLS])
    # 各ターゲットのスケールで正規化
    scale = np.array([y[t].std() for t in TARGET_COLS])
    distances = np.sqrt(np.sum(((preds - target_arr) / scale) ** 2, axis=1))

    top_idx = np.argsort(distances)[:n_top]

    results = cand_df.iloc[top_idx].copy()
    for i, t in enumerate(TARGET_COLS):
        results[f"predicted_{t}"] = preds[top_idx, i].round(2)
    results["distance"] = distances[top_idx].round(4)

    return results

# テスト: 高強度・高硬度の条件を探索
target = {"tensile_strength": 50, "elongation": 12, "hardness": 80}
recommendations = recommend_conditions(model, target)
print(f"目標: {target}")
print(f"\n推奨条件 Top 5:")
display(recommendations)
