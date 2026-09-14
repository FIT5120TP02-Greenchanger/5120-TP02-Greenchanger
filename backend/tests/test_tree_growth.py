import math

import pytest

from app.greening_model import tree_growth
from app.greening_model.tree_growth import load_model, predict_canopy

SPECIES = "Platanus x acerifolia"
TARGETS = ("canopy_m2", "height_m", "dbh_cm")


def lines():
    return load_model()["models"][SPECIES.lower()]

# test return value are these
def test_returns_every_field():
    result = predict_canopy(SPECIES, 5, size="M")
    assert set(result) == {
        "canopy_m2_min", "canopy_m2_max", "crown_width_m_min", "crown_width_m_max",
        "height_m_min", "height_m_max", "dbh_cm_min", "dbh_cm_max", "equivalent_age_years",
    }


@pytest.mark.parametrize("field", ["canopy_m2", "crown_width_m", "height_m", "dbh_cm"])
def test_every_range_grows_with_years(field):
    five = predict_canopy(SPECIES, 5, size="M")
    ten = predict_canopy(SPECIES, 10, size="M")
    assert 0 < five[f"{field}_min"] < five[f"{field}_max"]
    assert ten[f"{field}_min"] > five[f"{field}_min"]
    assert ten[f"{field}_max"] > five[f"{field}_max"]


@pytest.mark.parametrize("target", TARGETS)
def test_each_range_comes_from_its_own_p10_and_p90_lines(target):
    result = predict_canopy(SPECIES, 7, size="S")
    x = math.log1p(7)
    for end, name in (("min", "p10"), ("max", "p90")):
        a, b = lines()[target][name]
        assert result[f"{target}_{end}"] == round(math.exp(a + b * x), 1)


# test the canopy area and crown width are consistent with each other
def test_crown_width_is_the_diameter_of_the_canopy_area():
    result = predict_canopy(SPECIES, 10, size="L")
    for end in ("min", "max"):
        width = 2 * math.sqrt(result[f"canopy_m2_{end}"] / math.pi)
        assert math.isclose(result[f"crown_width_m_{end}"], width, abs_tol=0.1)


# test the height is the low is None when a species has no height line
def test_species_without_a_height_line_returns_none_for_height():
    species = next((sp for sp, s in load_model()["models"].items() if "height_m" not in s), None)
    if species is None:
        pytest.skip("every species in this model has a height line")
    result = predict_canopy(species, 0, size="S")
    assert result["height_m_min"] is None and result["height_m_max"] is None
    assert result["canopy_m2_min"] is not None

# test the larger size starts at an older equivalent age than a smaller size, for the same years
def test_larger_size_starts_older():
    small = predict_canopy(SPECIES, 5, size="S")
    large = predict_canopy(SPECIES, 5, size="L")
    assert large["equivalent_age_years"] > small["equivalent_age_years"]

# test the equivalent age is the same as the years for a new tree
def test_custom_start_width():
    result = predict_canopy(SPECIES, 5, start_width_m=3.0)
    assert 0 < result["canopy_m2_min"] < result["canopy_m2_max"]


def test_start_width_maps_back_to_the_same_crown():
    a, b = lines()["canopy_m2"]["p50"]
    age = predict_canopy(SPECIES, 0, start_width_m=3.0)["equivalent_age_years"]
    width = 2 * math.sqrt(math.exp(a + b * math.log1p(age)) / math.pi)
    assert math.isclose(width, 3.0, rel_tol=0.02)


def test_start_width_smaller_than_a_new_tree_starts_at_age_zero():
    assert predict_canopy(SPECIES, 0, start_width_m=0.01)["equivalent_age_years"] == 0


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"size": "M", "start_width_m": 2.0}, {"size": "XL"}, {"start_width_m": 0},
     {"start_width_m": float("nan")}],
)
def test_invalid_size_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        predict_canopy(SPECIES, 5, **kwargs)


def test_nan_years_raise():
    with pytest.raises(ValueError):
        predict_canopy(SPECIES, float("nan"), size="S")


def test_unsupported_species_raises():
    with pytest.raises(ValueError):
        predict_canopy("not a tree", 5, size="S")


def test_size_and_species_ignore_case_and_spaces():
    messy = predict_canopy(f" {SPECIES.upper()} ", 5, size="m")
    assert messy == predict_canopy(SPECIES, 5, size="M")


def test_oldest_training_age_is_allowed():
    max_age = lines()["max_age"]
    assert predict_canopy(SPECIES, max_age, size="S")["equivalent_age_years"] == max_age


@pytest.mark.parametrize("extra_years", [1, 1000])
def test_years_past_training_range_raise(extra_years):
    with pytest.raises(ValueError):
        predict_canopy(SPECIES, lines()["max_age"] + extra_years, size="S")


def test_cap_is_the_species_own_oldest_tree():
    species, youngest = min(load_model()["models"].items(), key=lambda kv: kv[1]["max_age"])
    with pytest.raises(ValueError):
        predict_canopy(species, youngest["max_age"] + 1, size="S")


def test_start_width_past_training_range_raises():
    with pytest.raises(ValueError):
        predict_canopy(SPECIES, 0, start_width_m=50.0)


def test_huge_start_width_is_a_value_error_for_every_species():
    # without the log-space check, flat median lines overflow math.expm1 (a 500, not a 422)
    for species in load_model()["models"]:
        with pytest.raises(ValueError):
            predict_canopy(species, 0, start_width_m=1e300)


def test_missing_model_file_raises_on_call(monkeypatch, tmp_path):
    monkeypatch.setattr(tree_growth, "MODEL_PATH", tmp_path / "missing.pkl")
    tree_growth.load_model.cache_clear()
    with pytest.raises(FileNotFoundError):
        predict_canopy(SPECIES, 5, size="S")
    tree_growth.load_model.cache_clear()


def test_every_range_is_ordered():
    # lines are straight in ln(age + 1): ordered at both ends means ordered at every age
    for s in load_model()["models"].values():
        for target in TARGETS:
            if target not in s:
                continue
            line = s[target]
            for age in (0, s["max_age"]):
                x = math.log1p(age)
                p10, p50, p90 = (line[n][0] + line[n][1] * x for n in ("p10", "p50", "p90"))
                assert p10 <= p50 <= p90
