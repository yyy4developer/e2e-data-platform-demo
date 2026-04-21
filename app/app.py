"""材料実験条件 予測・推薦アプリ

Serving Endpointに登録されたMLモデルを呼び出し、
配合条件から物性値を予測、または目標物性値から推奨条件を提案する。
"""

import os
import itertools
from typing import Optional

import numpy as np
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from databricks.sdk import WorkspaceClient

app = FastAPI(title="材料実験条件 予測・推薦アプリ")

ENDPOINT_NAME = os.environ.get("SERVING_ENDPOINT_NAME", "e2e-experiment-predictor")
TARGET_COLS = ["tensile_strength", "elongation", "hardness"]
FEATURE_COLS = [
    "material_a_ratio", "material_b_ratio", "temperature", "pressure",
    "ratio_interaction", "temp_pressure_interaction",
    "normalized_temperature", "normalized_pressure",
]


def get_client() -> WorkspaceClient:
    # Databricks App環境ではサービスプリンシパル経由で自動認証
    if os.environ.get("DATABRICKS_APP_NAME"):
        return WorkspaceClient()
    # ローカル実行時はDATABRICKS_PROFILEを指定（未指定時はDEFAULTプロファイル）
    profile = os.environ.get("DATABRICKS_PROFILE")
    return WorkspaceClient(profile=profile) if profile else WorkspaceClient()


def build_features(a_ratio: float, temperature: int, pressure: int) -> dict:
    """入力条件から全特徴量を計算する。"""
    b_ratio = round(1.0 - a_ratio, 2)
    return {
        "material_a_ratio": a_ratio,
        "material_b_ratio": b_ratio,
        "temperature": temperature,
        "pressure": pressure,
        "ratio_interaction": round(a_ratio * b_ratio, 4),
        "temp_pressure_interaction": round(temperature * pressure / 1000, 4),
        "normalized_temperature": round((temperature - 150) / 100, 4),
        "normalized_pressure": round((pressure - 30) / 70, 4),
    }


def predict_batch(records: list[dict]) -> list[list[float]]:
    """Serving Endpointでバッチ予測する。"""
    w = get_client()
    response = w.serving_endpoints.query(
        name=ENDPOINT_NAME,
        dataframe_records=records,
    )
    return response.predictions


# --- リクエスト/レスポンスモデル ---

class PredictRequest(BaseModel):
    material_a_ratio: float
    temperature: int
    pressure: int


class PredictResponse(BaseModel):
    tensile_strength: float
    elongation: float
    hardness: float
    result_grade: str


class RecommendRequest(BaseModel):
    target_tensile_strength: Optional[float] = 50.0
    target_elongation: Optional[float] = 12.0
    target_hardness: Optional[float] = 80.0
    top_n: int = 5


class RecommendItem(BaseModel):
    material_a_ratio: float
    temperature: int
    pressure: int
    predicted_tensile_strength: float
    predicted_elongation: float
    predicted_hardness: float
    predicted_grade: str
    distance: float


# --- APIエンドポイント ---

@app.get("/api/health")
def health():
    return {"status": "ok", "endpoint": ENDPOINT_NAME}


@app.post("/api/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    """配合条件から物性値を予測する。"""
    features = build_features(req.material_a_ratio, req.temperature, req.pressure)
    preds = predict_batch([features])
    ts, el, hd = preds[0]

    grade = "A" if ts >= 48 and hd >= 78 else ("B" if ts >= 38 and hd >= 65 else "C")

    return PredictResponse(
        tensile_strength=round(ts, 1),
        elongation=round(el, 1),
        hardness=round(hd, 0),
        result_grade=grade,
    )


@app.post("/api/recommend", response_model=list[RecommendItem])
def recommend(req: RecommendRequest):
    """目標物性値に最も近い配合条件をグリッドサーチで推薦する。"""
    # 探索グリッド
    a_ratios = np.arange(0.1, 0.91, 0.05)
    temps = np.arange(150, 251, 10)
    pressures = np.arange(30, 101, 10)

    candidates = []
    for a, t, p in itertools.product(a_ratios, temps, pressures):
        candidates.append(build_features(round(float(a), 2), int(t), int(p)))

    # バッチ予測（チャンクで分割）
    all_preds = []
    chunk_size = 500
    for i in range(0, len(candidates), chunk_size):
        chunk = candidates[i:i + chunk_size]
        preds = predict_batch(chunk)
        all_preds.extend(preds)

    # 目標との距離計算
    target = np.array([req.target_tensile_strength, req.target_elongation, req.target_hardness])
    preds_arr = np.array(all_preds)

    # 標準偏差でスケーリング
    scale = preds_arr.std(axis=0)
    scale[scale == 0] = 1.0
    distances = np.sqrt(np.sum(((preds_arr - target) / scale) ** 2, axis=1))

    # Top N
    top_idx = np.argsort(distances)[:req.top_n]

    results = []
    for idx in top_idx:
        c = candidates[idx]
        ts, el, hd = all_preds[idx]
        grade = "A" if ts >= 48 and hd >= 78 else ("B" if ts >= 38 and hd >= 65 else "C")
        results.append(RecommendItem(
            material_a_ratio=c["material_a_ratio"],
            temperature=c["temperature"],
            pressure=c["pressure"],
            predicted_tensile_strength=round(ts, 1),
            predicted_elongation=round(el, 1),
            predicted_hardness=round(hd, 0),
            predicted_grade=grade,
            distance=round(float(distances[idx]), 4),
        ))

    return results


# --- React Frontend Serving ---

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(frontend_dir, "index.html"))
