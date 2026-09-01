"""Reusable data preparation and analytics code for GreenChanger."""

from .classification import (
    classify_canopy_benchmark,
    classify_environmental_value,
    classify_melbourne_daily_mean_air_temperature,
)
from .measures import (
    canopy_gain_m2,
    estimated_heat_reduction_c,
    greening_gain_pct,
    projected_canopy_proxy_shade_m2,
    shade_projection_output,
)
from .intervention_model import (
    calculate_intervention_impact,
    evaluate_validation_cases,
    load_parameter_registry,
)
from .melbourne_sanity import (
    build_report as build_melbourne_sanity_report,
    evaluate_property_scenario,
    validate_scenario_set,
)
from .quality import QualityReport, validate_records
from .scenario_inputs import (
    calculate_simulated_action,
    load_input_contract,
    prepare_model_inputs,
)
from .residential_scenarios import (
    estimate_action_costs,
    evaluate_property_actions,
    load_cost_rows,
)

__all__ = [
    "QualityReport",
    "canopy_gain_m2",
    "build_melbourne_sanity_report",
    "calculate_intervention_impact",
    "calculate_simulated_action",
    "classify_canopy_benchmark",
    "classify_environmental_value",
    "classify_melbourne_daily_mean_air_temperature",
    "estimated_heat_reduction_c",
    "estimate_action_costs",
    "evaluate_validation_cases",
    "evaluate_property_scenario",
    "evaluate_property_actions",
    "greening_gain_pct",
    "projected_canopy_proxy_shade_m2",
    "shade_projection_output",
    "load_parameter_registry",
    "load_input_contract",
    "load_cost_rows",
    "prepare_model_inputs",
    "validate_records",
    "validate_scenario_set",
]
