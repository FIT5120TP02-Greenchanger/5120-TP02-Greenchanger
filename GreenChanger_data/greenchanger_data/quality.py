"""Record-level data-quality checks used by GreenChanger KPI 1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RuleResult:
    """Result of one quality rule across a dataset."""

    rule_code: str
    rule_type: str
    assessed_count: int
    passed_count: int
    failed_count: int
    pass_rate: float
    failed_indices: tuple[int, ...]


@dataclass(frozen=True)
class QualityReport:
    """Record-level quality summary for one dataset."""

    dataset_name: str
    threshold_pct: float
    total_records: int
    passing_records: int
    failing_records: int
    pass_rate: float
    passed_gate: bool
    failed_indices: tuple[int, ...]
    rule_results: tuple[RuleResult, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["failed_indices"] = list(self.failed_indices)
        for rule in result["rule_results"]:
            rule["failed_indices"] = list(rule["failed_indices"])
        return result


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _decimal(value: Any) -> Decimal | None:
    if _is_blank(value):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _normalise_key(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def _required_failures(
    records: Sequence[Mapping[str, Any]], rule: Mapping[str, Any]
) -> set[int]:
    fields = rule["fields"]
    return {
        index
        for index, record in enumerate(records)
        if any(_is_blank(record.get(field)) for field in fields)
    }


def _unique_failures(
    records: Sequence[Mapping[str, Any]], rule: Mapping[str, Any]
) -> set[int]:
    fields = rule["fields"]
    groups: dict[tuple[Any, ...], list[int]] = {}

    for index, record in enumerate(records):
        key = tuple(_normalise_key(record.get(field)) for field in fields)
        if any(_is_blank(value) for value in key):
            continue
        groups.setdefault(key, []).append(index)

    return {
        index
        for indices in groups.values()
        if len(indices) > 1
        for index in indices
    }


def _range_failures(
    records: Sequence[Mapping[str, Any]], rule: Mapping[str, Any]
) -> set[int]:
    field = rule["field"]
    minimum = _decimal(rule.get("minimum"))
    maximum = _decimal(rule.get("maximum"))
    inclusive_minimum = rule.get("inclusive_minimum", True)
    inclusive_maximum = rule.get("inclusive_maximum", True)
    allow_blank = rule.get("allow_blank", False)
    failures: set[int] = set()

    for index, record in enumerate(records):
        raw = record.get(field)
        if _is_blank(raw) and allow_blank:
            continue

        value = _decimal(raw)
        if value is None:
            failures.add(index)
            continue

        if minimum is not None:
            below_minimum = value < minimum if inclusive_minimum else value <= minimum
            if below_minimum:
                failures.add(index)
                continue

        if maximum is not None:
            above_maximum = value > maximum if inclusive_maximum else value >= maximum
            if above_maximum:
                failures.add(index)

    return failures


def _allowed_failures(
    records: Sequence[Mapping[str, Any]], rule: Mapping[str, Any]
) -> set[int]:
    field = rule["field"]
    allowed = {_normalise_key(value) for value in rule["values"]}
    return {
        index
        for index, record in enumerate(records)
        if _normalise_key(record.get(field)) not in allowed
    }


def _field_order_failures(
    records: Sequence[Mapping[str, Any]], rule: Mapping[str, Any]
) -> set[int]:
    lower_field = rule["lower_field"]
    upper_field = rule["upper_field"]
    failures: set[int] = set()

    for index, record in enumerate(records):
        lower = _decimal(record.get(lower_field))
        upper = _decimal(record.get(upper_field))
        if lower is None or upper is None or lower > upper:
            failures.add(index)

    return failures


RULE_HANDLERS = {
    "required": _required_failures,
    "unique": _unique_failures,
    "range": _range_failures,
    "allowed": _allowed_failures,
    "field_order": _field_order_failures,
}


def validate_records(
    dataset_name: str,
    records: Sequence[Mapping[str, Any]],
    rules: Sequence[Mapping[str, Any]],
    *,
    threshold_pct: float = 95.0,
) -> QualityReport:
    """Run configured rules and calculate a record-level quality pass rate.

    A record passes only when it passes every configured rule. Empty datasets
    receive a zero percent pass rate so missing extracts cannot pass the gate.
    """

    if not 0 <= threshold_pct <= 100:
        raise ValueError("threshold_pct must be between 0 and 100")

    total = len(records)
    all_failed_indices: set[int] = set()
    results: list[RuleResult] = []

    for rule in rules:
        rule_type = rule["type"]
        try:
            handler = RULE_HANDLERS[rule_type]
        except KeyError as error:
            raise ValueError(f"Unsupported quality rule type: {rule_type}") from error

        failed = handler(records, rule)
        all_failed_indices.update(failed)
        failed_count = len(failed)
        passed_count = total - failed_count
        pass_rate = round((passed_count / total * 100), 2) if total else 0.0
        results.append(
            RuleResult(
                rule_code=rule["code"],
                rule_type=rule_type,
                assessed_count=total,
                passed_count=passed_count,
                failed_count=failed_count,
                pass_rate=pass_rate,
                failed_indices=tuple(sorted(failed)),
            )
        )

    failing_records = len(all_failed_indices)
    passing_records = total - failing_records
    unrounded_pass_rate = passing_records / total * 100 if total else 0.0
    pass_rate = round(unrounded_pass_rate, 2)

    return QualityReport(
        dataset_name=dataset_name,
        threshold_pct=threshold_pct,
        total_records=total,
        passing_records=passing_records,
        failing_records=failing_records,
        pass_rate=pass_rate,
        passed_gate=total > 0 and unrounded_pass_rate >= threshold_pct,
        failed_indices=tuple(sorted(all_failed_indices)),
        rule_results=tuple(results),
    )


def validate_record_stream(
    dataset_name: str,
    records: Callable[[], Iterable[Mapping[str, Any]]],
    rules: Sequence[Mapping[str, Any]],
    *,
    threshold_pct: float = 95.0,
) -> QualityReport:
    """Validate a re-readable record stream without retaining all geometries.

    This is intended for metropolitan vector extracts whose polygon WKT can be
    several gigabytes. It supports the same configured rule types as
    ``validate_records`` and stores only failed indices and uniqueness keys.
    """

    if not 0 <= threshold_pct <= 100:
        raise ValueError("threshold_pct must be between 0 and 100")

    failed_by_rule: list[set[int]] = [set() for _ in rules]
    unique_first: list[dict[tuple[Any, ...], int] | None] = [
        {} if rule["type"] == "unique" else None for rule in rules
    ]
    total = 0
    for index, record in enumerate(records()):
        total += 1
        for position, rule in enumerate(rules):
            rule_type = rule["type"]
            if rule_type == "unique":
                fields = rule["fields"]
                key = tuple(_normalise_key(record.get(field)) for field in fields)
                if any(_is_blank(value) for value in key):
                    continue
                seen = unique_first[position]
                assert seen is not None
                first_index = seen.get(key)
                if first_index is None:
                    seen[key] = index
                else:
                    failed_by_rule[position].update((first_index, index))
                continue

            handler = RULE_HANDLERS.get(rule_type)
            if handler is None:
                raise ValueError(f"Unsupported quality rule type: {rule_type}")
            if handler([record], rule):
                failed_by_rule[position].add(index)

    all_failed = set().union(*failed_by_rule) if failed_by_rule else set()
    results: list[RuleResult] = []
    for rule, failed in zip(rules, failed_by_rule):
        failed_count = len(failed)
        passed_count = total - failed_count
        results.append(
            RuleResult(
                rule_code=rule["code"],
                rule_type=rule["type"],
                assessed_count=total,
                passed_count=passed_count,
                failed_count=failed_count,
                pass_rate=round(passed_count / total * 100, 2) if total else 0.0,
                failed_indices=tuple(sorted(failed)),
            )
        )

    failing_records = len(all_failed)
    passing_records = total - failing_records
    unrounded_pass_rate = passing_records / total * 100 if total else 0.0
    pass_rate = round(unrounded_pass_rate, 2)
    return QualityReport(
        dataset_name=dataset_name,
        threshold_pct=threshold_pct,
        total_records=total,
        passing_records=passing_records,
        failing_records=failing_records,
        pass_rate=pass_rate,
        passed_gate=total > 0 and unrounded_pass_rate >= threshold_pct,
        failed_indices=tuple(sorted(all_failed)),
        rule_results=tuple(results),
    )
