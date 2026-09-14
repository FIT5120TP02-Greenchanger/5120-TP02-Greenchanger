import math
import pickle
from pathlib import Path

import numpy as np

# model trained in ml/train.ipynb, loaded once at import
with open(Path(__file__).parent / "config" / "tree_canopy_growth_model.pkl", "rb") as f:
    MODEL = pickle.load(f)


def predict_canopy(species, years, size=None, start_width_m=None):
    fits = MODEL["models"].get(species.lower())

    # check if the input parameters are valid
    if fits is None:
        raise ValueError("unsupported species")
    if years < 0:
        raise ValueError("years must be >= 0")
    if (size is None) == (start_width_m is None):
        raise ValueError("give exactly one of size or start_width_m")

    if size is not None:
        if size not in MODEL["size_offset_years"]:
            raise ValueError("size must be S, M or L")
        age0 = float(MODEL["size_offset_years"][size])
    else:
        if start_width_m <= 0:
            raise ValueError("start_width_m must be > 0")
        a50, b50 = fits["p50"].params
        start_area = math.pi * (start_width_m / 2) ** 2
        age0 = max(0.0, (math.log(start_area) - a50) / b50)

    age = age0 + years
    X = np.array([[1.0, age]])
    lo = float(np.exp(fits["p10"].predict(X))[0])
    hi = float(np.exp(fits["p90"].predict(X))[0])
    lo, hi = min(lo, hi), max(lo, hi)

    min_age, max_age = MODEL["valid_age_range"]
    return {
        "canopy_m2_min": round(lo, 1),
        "canopy_m2_max": round(hi, 1),
        "equivalent_age_years": round(age, 1),
        "outside_training_range": not (min_age <= age <= max_age),
    }
