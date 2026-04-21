# Databricks notebook source
# MAGIC %md
# MAGIC # Model Serving Endpoint のデプロイ
# MAGIC
# MAGIC UC Model Registryに登録済みのモデルを
# MAGIC サーバーレスServing Endpointとしてデプロイする。

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_use_yao_catalog", "カタログ名")
dbutils.widgets.text("schema", "km_e2e_demo", "スキーマ名")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

model_name = f"{catalog}.{schema}.experiment_predictor"
endpoint_name = "km-experiment-predictor"

print(f"モデル: {model_name}")
print(f"エンドポイント: {endpoint_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 最新モデルバージョンの取得

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

versions = list(w.model_versions.list(full_name=model_name))
latest_version = max(int(v.version) for v in versions)
print(f"最新バージョン: {latest_version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Serving Endpoint の作成/更新

# COMMAND ----------

from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput

config = EndpointCoreConfigInput(
    served_entities=[
        ServedEntityInput(
            entity_name=model_name,
            entity_version=str(latest_version),
            workload_size="Small",
            scale_to_zero_enabled=True,
        )
    ]
)

# 既存チェック
try:
    existing = w.serving_endpoints.get(name=endpoint_name)
    print(f"エンドポイント {endpoint_name} を更新中...")
    w.serving_endpoints.update_config(name=endpoint_name, served_entities=config.served_entities)
except Exception:
    print(f"エンドポイント {endpoint_name} を新規作成中...")
    w.serving_endpoints.create(name=endpoint_name, config=config)

print("デプロイリクエスト完了")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. エンドポイントの準備完了を待機

# COMMAND ----------

import time

print(f"エンドポイント {endpoint_name} の準備を待機中...")
for i in range(60):
    ep = w.serving_endpoints.get(name=endpoint_name)
    state = ep.state
    print(f"  [{i+1}] ready={state.ready}, config_update={state.config_update}")
    if str(state.ready) == "READY":
        print(f"\nエンドポイント準備完了!")
        break
    time.sleep(15)
else:
    print("タイムアウト（バックグラウンドで続行中）")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. テスト推論

# COMMAND ----------

test_data = {
    "dataframe_records": [
        {
            "material_a_ratio": 0.7,
            "material_b_ratio": 0.3,
            "temperature": 190,
            "pressure": 80,
            "ratio_interaction": 0.21,
            "temp_pressure_interaction": 15.2,
            "normalized_temperature": 0.4,
            "normalized_pressure": 0.714,
        }
    ]
}

try:
    response = w.serving_endpoints.query(name=endpoint_name, dataframe_records=test_data["dataframe_records"])
    print("テスト推論成功:")
    print(response)
except Exception as e:
    print(f"テスト推論: {e} (エンドポイントがまだ準備中の場合あり)")
