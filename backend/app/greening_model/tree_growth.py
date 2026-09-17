import math
import pickle
from functools import cache
from pathlib import Path

# load the trained model from the config directory, relative to this file
MODEL_PATH = Path(__file__).parent / "config" / "tree_canopy_growth_model.pkl"

# years of head start for each nursery size: a product assumption, not learned from data
# (keep in step with the S / M / L sizes in frontend/src/hooks/simulation.js)
SIZE_OFFSET_YEARS = {"S": 0, "M": 5, "L": 10}


# model trained in ml/train.ipynb (Port Phillip inventory), loaded on first call
# so a missing or bad file only breaks this feature, not the whole API
@cache
def load_model():
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def _range(lines, target, x):
    # p10 and p90 of one target at x = ln(age + 1); None when this species has no line for it
    if target not in lines:
        return None, None
    (a10, b10), (a90, b90) = lines[target]["p10"], lines[target]["p90"]
    return math.exp(a10 + b10 * x), math.exp(a90 + b90 * x)


def _point(lines, target, x):
    # p50 (median) of one target at x = ln(age + 1) -- the model's actual central
    # estimate, not a naive average of p10/p90 (these are log-linear fits, so the
    # arithmetic midpoint of the two bounds is not the same value as the p50 line).
    if target not in lines:
        return None
    a50, b50 = lines[target]["p50"]
    return math.exp(a50 + b50 * x)


def _round(value):
    return None if value is None else round(value, 1)


def predict_canopy(species, years, size=None, start_width_m=None):
    model = load_model()
    lines = model["models"].get(species.strip().lower())

    # check if the input parameters are valid ("not >=" also rejects NaN)
    if lines is None:
        raise ValueError("unsupported species")
    if not years >= 0:
        raise ValueError("years must be >= 0")
    if (size is None) == (start_width_m is None):
        raise ValueError("give exactly one of size or start_width_m")

    # each line is ln(value) = a + b * ln(age + 1), trusted up to this species' oldest training tree
    max_age = lines["max_age"]
    if size is not None:
        size = str(size).upper()
        if size not in SIZE_OFFSET_YEARS:
            raise ValueError("size must be S, M or L")
        age0 = float(SIZE_OFFSET_YEARS[size])
    else:
        if not start_width_m > 0:
            raise ValueError("start_width_m must be > 0")
        # invert the median crown line in log space, so extreme widths cannot overflow
        a50, b50 = lines["canopy_m2"]["p50"]
        t = (math.log(math.pi / 4) + 2 * math.log(start_width_m) - a50) / b50
        if t > math.log1p(max_age):
            raise ValueError(f"start_width_m is past the training range (max age {max_age})")
        age0 = max(0.0, math.expm1(t))

    age = age0 + years
    if age > max_age:
        raise ValueError(f"equivalent age {age:.4g} is past the training range (max {max_age})")

    # training kept only lines where p10 stays below p90 at every age, so min never exceeds max
    x = math.log1p(age)
    area = _range(lines, "canopy_m2", x)
    height = _range(lines, "height_m", x)
    dbh = _range(lines, "dbh_cm", x)
    area_median = _point(lines, "canopy_m2", x)
    height_median = _point(lines, "height_m", x)
    dbh_median = _point(lines, "dbh_cm", x)
    # crown width is the diameter of a circle with that area
    width = [2 * math.sqrt(a / math.pi) for a in area]
    width_median = 2 * math.sqrt(area_median / math.pi) if area_median is not None else None
    return {
        "canopy_m2_min": _round(area[0]),
        "canopy_m2_max": _round(area[1]),
        "canopy_m2_median": _round(area_median),
        "crown_width_m_min": _round(width[0]),
        "crown_width_m_max": _round(width[1]),
        "crown_width_m_median": _round(width_median),
        "height_m_min": _round(height[0]),
        "height_m_max": _round(height[1]),
        "height_m_median": _round(height_median),
        "dbh_cm_min": _round(dbh[0]),
        "dbh_cm_max": _round(dbh[1]),
        "dbh_cm_median": _round(dbh_median),
        "equivalent_age_years": round(age, 1),
    }
