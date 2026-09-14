import pytest

from app.greening_model.tree_growth import predict_canopy

SPECIES = "Platanus x acerifolia"

def test_size_preset_range_grows_with_years():
    five = predict_canopy(SPECIES, 5, size="M")
    ten = predict_canopy(SPECIES, 10, size="M")
    assert 0 < five["canopy_m2_min"] < five["canopy_m2_max"]
    assert ten["canopy_m2_min"] > five["canopy_m2_min"]
    assert ten["canopy_m2_max"] > five["canopy_m2_max"]


def test_larger_size_starts_older():
    small = predict_canopy(SPECIES, 5, size="S")
    large = predict_canopy(SPECIES, 5, size="L")
    assert large["equivalent_age_years"] > small["equivalent_age_years"]


def test_custom_start_width():
    result = predict_canopy(SPECIES, 5, start_width_m=3.0)
    assert 0 < result["canopy_m2_min"] < result["canopy_m2_max"]


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"size": "M", "start_width_m": 2.0}, {"size": "XL"}, {"start_width_m": 0}],
)
def test_invalid_size_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        predict_canopy(SPECIES, 5, **kwargs)


def test_unsupported_species_raises():
    with pytest.raises(ValueError):
        predict_canopy("not a tree", 5, size="S")