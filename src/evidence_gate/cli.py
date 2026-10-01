from __future__ import annotations

import argparse
import json
import sys
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from evidence_gate.json_data import parse_json
from evidence_gate.models import RunBundle, ValidationResult
from evidence_gate.reports import write_review_packet_file, write_status_json
from evidence_gate.specs import SpecValidationError, load_spec
from evidence_gate.validators import validate_run

SPEC_ERROR_EXIT_CODE = 2


class CliInputError(ValueError):
    """Raised for expected CLI input problems that should not print tracebacks."""


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args)
        if args.command == "packet":
            return _packet(args)
        if args.command == "init-example":
            return _init_example(args)
    except SpecValidationError as exc:
        sys.stderr.write(f"spec error: {exc}\n")
        return SPEC_ERROR_EXIT_CODE
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"input error: invalid JSON: {exc.msg}\n")
        return SPEC_ERROR_EXIT_CODE
    except (CliInputError, KeyError, TypeError, ValueError) as exc:
        sys.stderr.write(f"input error: {exc}\n")
        return SPEC_ERROR_EXIT_CODE
    except OSError as exc:
        sys.stderr.write(f"file error: {exc}\n")
        return SPEC_ERROR_EXIT_CODE
    parser.print_help()
    return SPEC_ERROR_EXIT_CODE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-gate")
    subparsers = parser.add_subparsers(dest="command")

    validate = subparsers.add_parser("validate", help="validate a run directory against a spec")
    validate.add_argument("--spec", required=True, type=Path)
    validate.add_argument("--run", required=True, type=Path)
    validate.add_argument("--json-out", type=Path)

    packet = subparsers.add_parser("packet", help="write a Markdown review packet from status JSON")
    packet.add_argument("--status", required=True, type=Path)
    packet.add_argument("--md-out", required=True, type=Path)

    example = subparsers.add_parser("init-example", help="copy the bundled synthetic example")
    example.add_argument("target", type=Path)
    return parser


def _validate(args: argparse.Namespace) -> int:
    result = validate_run(RunBundle(args.run), load_spec(args.spec))
    if args.json_out:
        write_status_json(result, args.json_out)
    else:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    return 0 if result.passed else 1


def _packet(args: argparse.Namespace) -> int:
    payload = parse_json(args.status.read_text(encoding="utf-8"))
    result = ValidationResult.from_dict(payload)
    write_review_packet_file(result, args.md_out, markdown=True)
    return 0


def _init_example(args: argparse.Namespace) -> int:
    source = resources.files("evidence_gate").joinpath("examples", "toy-ml-run")
    if args.target.exists():
        raise CliInputError(f"target already exists: {args.target}")
    _copy_tree(source, args.target)
    return 0


def _copy_tree(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True)
    for child in source.iterdir():
        child_target = target / child.name
        if child.is_dir():
            _copy_tree(child, child_target)
        else:
            child_target.write_bytes(child.read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
