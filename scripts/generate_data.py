"""材料研究実験データの合成生成スクリプト

KM E2Eデモ用。材料の配合条件と物性測定値に
現実的な相関を持たせ、MLモデルが学習可能なデータを生成する。

Tier 1: Polars + NumPy（ローカルCSV出力）
実行: uv run scripts/generate_data.py
"""

import numpy as np
import polars as pl
from pathlib import Path

SEED = 42
NUM_ROWS = 10_000
OUTPUT = Path(__file__).parent.parent / "data" / "sample_experiments.csv"

rng = np.random.default_rng(SEED)

# --- experiment_id（実験ID） ---
experiment_id = np.array([f"EXP-{i:05d}" for i in range(1, NUM_ROWS + 1)])

# --- experiment_date（実験日）: 2025-01-01 〜 2026-04-01 ---
start = np.datetime64("2025-01-01")
span = (np.datetime64("2026-04-01") - start).astype(int)
experiment_date = start + rng.integers(0, span + 1, size=NUM_ROWS).astype("timedelta64[D]")

# --- 配合条件 ---
material_a_ratio = np.round(rng.uniform(0.10, 0.90, size=NUM_ROWS), 2)  # 材料A配合比
material_b_ratio = np.round(1.0 - material_a_ratio, 2)                   # 材料B配合比
temperature = rng.integers(150, 251, size=NUM_ROWS)   # 温度 (℃)
pressure = rng.integers(30, 101, size=NUM_ROWS)        # 圧力 (MPa)

# --- 物性値（相関あり + ノイズ） ---
# tensile_strength（引張強度）: 高A比 + 温度~190℃付近 → 高値
temp_factor = 1.0 - np.abs(temperature - 190) / 100.0
a_factor = material_a_ratio * 1.5
pressure_factor = pressure / 100.0

tensile_strength = np.round(
    30 + 20 * a_factor * temp_factor + 5 * pressure_factor
    + rng.normal(0, 3, size=NUM_ROWS), 1
)
tensile_strength = np.maximum(tensile_strength, 10.0)

# elongation（伸び率）: 引張強度と逆相関
elongation = np.round(
    25 - 0.3 * tensile_strength + 10 * (1 - material_a_ratio)
    + rng.normal(0, 2, size=NUM_ROWS), 1
)
elongation = np.maximum(elongation, 1.0)

# hardness（硬度）: A比と圧力に正の相関
hardness = np.round(
    50 + 30 * material_a_ratio + 15 * pressure_factor
    + rng.normal(0, 4, size=NUM_ROWS), 0
).astype(int)
hardness = np.maximum(hardness, 20)

# --- result_grade（判定結果） ---
# 閾値調整: A約20%, B約55%, C約23%
result_grade = np.where(
    (tensile_strength >= 48) & (hardness >= 78), "A",
    np.where((tensile_strength >= 38) & (hardness >= 65), "B", "C")
)

# --- DataFrame 構築 ---
df = pl.DataFrame({
    "experiment_id": experiment_id,
    "experiment_date": experiment_date,
    "material_a_ratio": material_a_ratio,
    "material_b_ratio": material_b_ratio,
    "temperature": temperature,
    "pressure": pressure,
    "tensile_strength": tensile_strength,
    "elongation": elongation,
    "hardness": hardness,
    "result_grade": result_grade,
})

# --- 出力 ---
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
df.write_csv(OUTPUT)

# --- サマリー ---
print(f"生成完了: {NUM_ROWS:,} 行 → {OUTPUT}")
print(f"\n判定結果の分布:")
for grade in ["A", "B", "C"]:
    count = int((result_grade == grade).sum())
    print(f"  {grade}: {count:,} ({count/NUM_ROWS*100:.1f}%)")

print(f"\n先頭5行:")
print(df.head(5))
