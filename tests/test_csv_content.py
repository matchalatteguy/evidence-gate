from __future__ import annotations

import hashlib
import json
from decimal import localcontext
from pathlib import Path

import pytest
import yaml

from evidence_gate import RunBundle, load_spec, validate_run
from evidence_gate.csv_checks import validate_csv
from evidence_gate.models import Check, CsvColumnSpec, CsvSpec


def _checks(
    tmp_path: Path,
    contents: str | bytes,
    spec: CsvSpec,
    *,
    expected_columns: list[str] | None = None,
    payload: dict | None = None,
) -> list[Check]:
    path = tmp_path / "data.csv"
    path.write_bytes(contents.encode() if isinstance(contents, str) else contents)
    return validate_csv(path, spec, expected_columns or [], payload or {}, "metrics", "data.csv")


def _failures(checks: list[Check]) -> dict[str, Check]:
    return {check.code: check for check in checks if check.severity == "failure"}


def test_multiline_csv_counts_records_and_checks_typed_cells(tmp_path: Path) -> None:
    checks = _checks(
        tmp_path,
        'id,note,score\n+1,"first\nsecond, quoted ""text""",0.125\n2,ok,1e-3\n',
        CsvSpec(
            rows={"min": 2, "max": 2},
            row_count_field="summary.exported_rows",
            columns={
                "id": CsvColumnSpec(type="integer", min=0),
                "note": CsvColumnSpec(),
                "score": CsvColumnSpec(type="number", min=0, max=1),
            },
        ),
        payload={"summary": {"exported_rows": 2}},
    )
    assert not _failures(checks)
    assert {check.code for check in checks} == {"table.content", "table.row_count"}
    count = next(check for check in checks if check.code == "table.row_count")
    assert count.details == {"actual_rows": 2, "expected": {"min": 2, "max": 2}, "expected_rows": 2}


def test_diagnostics_use_physical_start_lines_after_multiline_records(tmp_path: Path) -> None:
    failures = _failures(
        _checks(
            tmp_path,
            'id,note\n1,"a\nb"\nwrong,ok\n',
            CsvSpec(columns={"id": CsvColumnSpec(type="integer")}),
        )
    )
    assert failures["table.invalid_integer"].details["first_rows"] == [4]


@pytest.mark.parametrize("contents", ["", "\n", "id,\n", "id, \n", "id,id\n1,2\n"])
def test_header_must_exist_and_have_unique_nonblank_names(tmp_path: Path, contents: str) -> None:
    failures = _failures(_checks(tmp_path, contents, CsvSpec()))
    assert set(failures) == {"table.invalid_header"}


def test_configured_and_legacy_required_columns_are_both_enforced(tmp_path: Path) -> None:
    failures = _failures(
        _checks(
            tmp_path,
            "present\nvalue\n",
            CsvSpec(columns={"typed": CsvColumnSpec(type="integer")}),
            expected_columns=["legacy"],
        )
    )
    assert failures["table.column_missing"].details == {
        "missing_count": 2,
        "columns": ["legacy", "typed"],
    }


def test_missing_extra_and_blank_records_fail_width_checks(tmp_path: Path) -> None:
    checks = _checks(
        tmp_path,
        "id,score\n1\n2,0.5,extra\n\n3,0.2\n",
        CsvSpec(rows={"min": 4, "max": 4}, columns={"id": CsvColumnSpec(type="integer")}),
    )
    failures = _failures(checks)
    assert set(failures) == {"table.row_width"}
    assert failures["table.row_width"].details == {"occurrences": 3, "first_rows": [2, 3, 4]}
    assert (
        next(check for check in checks if check.code == "table.row_count").details["actual_rows"]
        == 4
    )


@pytest.mark.parametrize("contents", ['id,note\n1,"unterminated\n', 'id,note\n1,"closed"bad\n'])
def test_strict_parser_failure_does_not_evaluate_partial_row_counts(
    tmp_path: Path, contents: str
) -> None:
    checks = _checks(tmp_path, contents, CsvSpec(rows={"min": 2}, row_count_field="counts.rows"))
    assert set(_failures(checks)) == {"table.invalid_csv"}
    assert not any(check.code.startswith("table.row_count") for check in checks)
    assert _failures(checks)["table.invalid_csv"].details["complete"] is False


def test_invalid_utf8_fails_even_when_header_is_plain_ascii(tmp_path: Path) -> None:
    failures = _failures(_checks(tmp_path, b"id,note\n1,\xff\n", CsvSpec()))
    assert failures["table.invalid_csv"].details["error_type"] == "UnicodeDecodeError"


def test_read_error_is_bounded_and_does_not_expose_exception_text(
    tmp_path: Path, monkeypatch
) -> None:
    original = Path.open

    def denied(path, *args, **kwargs):
        if path.name == "data.csv" and args == () and kwargs.get("mode", "r") == "r":
            raise PermissionError("sensitive exception text")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    checks = _checks(tmp_path, "id\n1\n", CsvSpec())
    assert _failures(checks)["table.invalid_csv"].details["error_type"] == "PermissionError"
    assert "sensitive" not in json.dumps([check.to_dict() for check in checks])


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "Inf", "not-a-number"])
def test_numeric_cells_require_finite_numbers(tmp_path: Path, value: str) -> None:
    failures = _failures(
        _checks(
            tmp_path, f"score\n{value}\n", CsvSpec(columns={"score": CsvColumnSpec(type="number")})
        )
    )
    assert set(failures) == {"table.invalid_number"}


@pytest.mark.parametrize(
    "value", ["1_000", "1__0", "\u0661.\u0662", "\u0661e\u0662", "1e\u0662", "0x10", "1 2"]
)
def test_number_cells_reject_nonportable_decimal_lexemes(tmp_path: Path, value: str) -> None:
    failures = _failures(
        _checks(
            tmp_path, f"score\n{value}\n", CsvSpec(columns={"score": CsvColumnSpec(type="number")})
        )
    )
    assert set(failures) == {"table.invalid_number"}


@pytest.mark.parametrize("value", ["  +1.25e-2  ", "-.5", "1.", "+0", "-2E+03"])
def test_number_cells_accept_ascii_decimal_scientific_and_surrounding_whitespace(
    tmp_path: Path, value: str
) -> None:
    checks = _checks(
        tmp_path, f"score\n{value}\n", CsvSpec(columns={"score": CsvColumnSpec(type="number")})
    )
    assert not _failures(checks)


@pytest.mark.parametrize("value", ["1.0", "1e3", "\u0661", " 2", "2 ", "+", "--2", "word"])
def test_integer_cells_require_ascii_integer_lexemes(tmp_path: Path, value: str) -> None:
    failures = _failures(
        _checks(tmp_path, f"id\n{value}\n", CsvSpec(columns={"id": CsvColumnSpec(type="integer")}))
    )
    assert set(failures) == {"table.invalid_integer"}


def test_large_integer_and_numeric_limits_do_not_round(tmp_path: Path) -> None:
    limit = 2**100 + 1
    with localcontext() as context:
        context.prec = 2
        checks = _checks(
            tmp_path,
            f"id,score\n{limit},0.1\n{limit - 1},0.0999999999999999999999999\n"
            f"{limit + 1},0.1000000000000000000000001\n",
            CsvSpec(
                columns={
                    "id": CsvColumnSpec(type="integer", min=limit, max=limit),
                    "score": CsvColumnSpec(type="number", min=0.1, max=0.1),
                }
            ),
        )
    failures = _failures(checks)
    assert set(failures) == {"table.value_below_min", "table.value_above_max"}
    assert failures["table.value_below_min"].details["occurrences"] == 2
    assert failures["table.value_above_max"].details["occurrences"] == 2


def test_optional_empty_cells_skip_type_checks_but_required_cells_fail(tmp_path: Path) -> None:
    spec = CsvSpec(
        columns={
            "required": CsvColumnSpec(),
            "optional": CsvColumnSpec(type="integer", non_empty=False),
        }
    )
    checks = _checks(tmp_path, 'required,optional\nok,""\nok, \n', spec)
    assert not _failures(checks)
    failures = _failures(_checks(tmp_path, 'required,optional\n"",\n', spec))
    assert set(failures) == {"table.empty_cell"}


@pytest.mark.parametrize("expected", [None, True, False, -1, 1.0, 1.5, "1", [], {}])
def test_producer_row_count_must_be_a_nonnegative_integer(tmp_path: Path, expected: object) -> None:
    failures = _failures(
        _checks(
            tmp_path,
            "id\n1\n",
            CsvSpec(row_count_field="summary.rows"),
            payload={"summary": {"rows": expected}},
        )
    )
    assert set(failures) == {"table.row_count_invalid"}
    assert failures["table.row_count_invalid"].details["actual_rows"] == 1


def test_missing_producer_row_count_and_nonobject_intermediate_fail(tmp_path: Path) -> None:
    for payload in ({}, {"summary": []}):
        assert set(
            _failures(
                _checks(
                    tmp_path, "id\n1\n", CsvSpec(row_count_field="summary.rows"), payload=payload
                )
            )
        ) == {"table.row_count_invalid"}


def test_row_count_mismatch_preserves_exact_expected_integer(tmp_path: Path) -> None:
    expected = 2**60 + 1
    failures = _failures(
        _checks(
            tmp_path,
            "id\n1\n",
            CsvSpec(row_count_field="counts.rows"),
            payload={"counts": {"rows": expected}},
        )
    )
    assert failures["table.row_count_mismatch"].details == {
        "actual_rows": 1,
        "expected_rows": expected,
    }


@pytest.mark.parametrize(
    ("contents", "rows", "code"),
    [
        ("id\n", {"min": 1}, "table.row_count_below_min"),
        ("id\n1\n2\n", {"max": 1}, "table.row_count_above_max"),
    ],
)
def test_data_row_thresholds_fail(tmp_path: Path, contents: str, rows: dict, code: str) -> None:
    assert set(_failures(_checks(tmp_path, contents, CsvSpec(rows=rows)))) == {code}


def test_zero_rows_can_be_explicitly_allowed(tmp_path: Path) -> None:
    checks = _checks(
        tmp_path,
        "id\n",
        CsvSpec(rows={"min": 0, "max": 0}, row_count_field="counts.rows"),
        payload={"counts": {"rows": 0}},
    )
    assert not _failures(checks)
    assert (
        next(check for check in checks if check.code == "table.content").details["actual_rows"] == 0
    )


def test_all_rows_are_read_incrementally_and_error_samples_remain_bounded(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "large.csv"
    with path.open("w") as handle:
        handle.write("id,score\n")
        for index in range(10000):
            value = "private-cell-value" if index % 1000 == 0 else str(index)
            handle.write(f"{value},0.5\n")

    class IteratorOnly:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.handle)

        def read(self, *args):
            raise AssertionError("CSV validation must not read the full file")

        def readlines(self, *args):
            raise AssertionError("CSV validation must not retain all lines")

    original = Path.open

    def guarded_open(candidate, *args, **kwargs):
        handle = original(candidate, *args, **kwargs)
        return IteratorOnly(handle) if candidate == path else handle

    monkeypatch.setattr(Path, "open", guarded_open)
    checks = validate_csv(
        path,
        CsvSpec(rows={"min": 10000, "max": 10000}, columns={"id": CsvColumnSpec(type="integer")}),
        [],
        {},
        "metrics",
        "large.csv",
    )
    assert len(checks) == 2
    details = _failures(checks)["table.invalid_integer"].details
    assert details == {
        "occurrences": 10,
        "first_rows": [2, 1002, 2002, 3002, 4002],
        "columns": ["id"],
    }
    assert (
        next(check for check in checks if check.code == "table.row_count").details["actual_rows"]
        == 10000
    )
    assert "private-cell-value" not in json.dumps([check.to_dict() for check in checks])


@pytest.mark.parametrize(
    ("contents", "code"),
    [
        (b"", "table.invalid_header"),
        (b"id,label,score\n", "table.row_count_below_min"),
        (b"id,label,score\n1,cat\n", "table.row_width"),
        (b"id,label,score\n1,cat,NaN\n", "table.invalid_number"),
    ],
)
def test_correct_digest_cannot_bless_invalid_or_incomplete_csv(
    demo_run: tuple[Path, Path], contents: bytes, code: str
) -> None:
    spec_path, run = demo_run
    contract = yaml.safe_load(spec_path.read_text())
    output = contract["reports"][0]["outputs"]["predictions"]
    output["sha256_field"] = "sha256.predictions"
    output["csv"] = {
        "rows": {"min": 2},
        "row_count_field": "counts.examples",
        "columns": {"id": {"type": "integer"}, "score": {"type": "number", "min": 0, "max": 1}},
    }
    spec_path.write_text(json.dumps(contract))
    artifact = run / "artifacts/predictions.csv"
    artifact.write_bytes(contents)
    report_path = run / "reports/metrics.json"
    payload = json.loads(report_path.read_text())
    payload["sha256"] = {"predictions": hashlib.sha256(contents).hexdigest()}
    report_path.write_text(json.dumps(payload))
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert not result.passed
    assert code in {check.code for check in result.failures}
    assert "artifact.sha256_match" in {check.code for check in result.checks}


def test_legacy_header_only_configuration_still_accepts_header_only_csv(
    demo_run: tuple[Path, Path],
) -> None:
    spec_path, run = demo_run
    (run / "artifacts/predictions.csv").write_text("id,label,score\n")
    result = validate_run(RunBundle(run), load_spec(spec_path))
    assert result.passed
    assert "table.columns" in {check.code for check in result.checks}
    assert "table.content" not in {check.code for check in result.checks}
