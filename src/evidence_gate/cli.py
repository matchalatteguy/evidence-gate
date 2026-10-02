from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unicodedata
from importlib import metadata, resources
from importlib.resources.abc import Traversable
from pathlib import Path

from evidence_gate.json_data import parse_json
from evidence_gate.models import RunBundle, ValidationResult
from evidence_gate.producers import _json_object_bytes
from evidence_gate.reports import render_junit_xml, render_review_packet
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
        if args.command == "check-spec":
            spec = load_spec(args.spec)
            sys.stdout.write(f"Contract valid: {len(spec.reports)} reports\n")
            return 0
        if args.command == "init-example":
            return _init_example(args)
    except SpecValidationError as exc:
        sys.stderr.write(f"spec error: {exc}; no usable result produced\n")
        return SPEC_ERROR_EXIT_CODE
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"input error: invalid JSON: {exc.msg}; no usable result produced\n")
        return SPEC_ERROR_EXIT_CODE
    except (CliInputError, KeyError, TypeError, ValueError) as exc:
        sys.stderr.write(f"input error: {exc}; no usable result produced\n")
        return SPEC_ERROR_EXIT_CODE
    except OSError as exc:
        sys.stderr.write(f"file error: {exc}; no usable result produced\n")
        return SPEC_ERROR_EXIT_CODE
    parser.print_help()
    return SPEC_ERROR_EXIT_CODE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-gate")
    try:
        installed_version = metadata.version("evidence-gate")
    except metadata.PackageNotFoundError:
        installed_version = "uninstalled"
    parser.add_argument("--version", action="version", version=f"%(prog)s {installed_version}")
    subparsers = parser.add_subparsers(dest="command")

    validate = subparsers.add_parser("validate", help="validate a run directory against a spec")
    validate.add_argument("--spec", required=True, type=Path)
    validate.add_argument("--run", required=True, type=Path)
    validate.add_argument("--json-out", type=Path)
    validate.add_argument("--md-out", type=Path)
    validate.add_argument("--junit-out", type=Path)
    validate.add_argument("--baseline", type=Path)
    validate.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Treat optional-evidence warnings as failures",
    )

    check_spec = subparsers.add_parser(
        "check-spec", help="validate a contract without running evidence checks"
    )
    check_spec.add_argument("--spec", required=True, type=Path)

    packet = subparsers.add_parser("packet", help="write a Markdown review packet from status JSON")
    packet.add_argument("--status", required=True, type=Path)
    packet.add_argument("--md-out", required=True, type=Path)

    example = subparsers.add_parser("init-example", help="copy the bundled synthetic example")
    example.add_argument("target", type=Path)
    example.add_argument("--name", choices=["toy-ml-run", "model-promotion"], default="toy-ml-run")
    return parser


class _OutputBatch:
    """Preflight and stage all outputs before publishing individually atomic files."""

    def __init__(self, targets: list[Path], inputs: list[Path], run_roots: list[Path]):
        self.targets = targets
        self.inputs = inputs
        self.run_roots = run_roots
        self.staged: dict[Path, Path] = {}
        self.resolved_targets: dict[Path, Path] = {}

    def __enter__(self) -> _OutputBatch:
        try:
            self._preflight()
            for target in self.targets:
                destination = self.resolved_targets[target]
                destination.parent.mkdir(parents=True, exist_ok=True)
                descriptor, name = tempfile.mkstemp(
                    dir=destination.parent, prefix=".evidence-gate-"
                )
                os.close(descriptor)
                self.staged[target] = Path(name)
        except BaseException:
            self._cleanup()
            raise
        return self

    def _preflight(self) -> None:
        try:
            resolved = [target.resolve() for target in self.targets]
            source_paths = {_path_key(path.resolve()) for path in self.inputs}
            roots = [_path_key(root.resolve()) for root in self.run_roots]
        except RuntimeError as exc:
            raise CliInputError("output/input paths could not be resolved") from exc
        destination_keys = [_path_key(path) for path in resolved]
        if len(set(destination_keys)) != len(destination_keys):
            raise CliInputError(
                "output paths must be distinct ignoring case and Unicode normalization"
            )
        self.resolved_targets = dict(zip(self.targets, resolved, strict=True))
        source_ids = set()
        for path in self.inputs:
            if path.is_file():
                info = path.stat()
                source_ids.add((info.st_dev, info.st_ino))
        destination_ids = set()
        for target, canonical, key in zip(self.targets, resolved, destination_keys, strict=True):
            if target.is_symlink():
                raise CliInputError("output destinations cannot be symbolic links")
            if key in source_paths or any(
                key == root or key.startswith(root.rstrip("/") + "/") for root in roots
            ):
                raise CliInputError(
                    "outputs cannot replace inputs or be inside candidate/baseline run roots"
                )
            if canonical.exists():
                if not canonical.is_file():
                    raise CliInputError(f"output destination must be a regular file: {target}")
                info = canonical.stat()
                if info.st_nlink > 1:
                    raise CliInputError("output destinations cannot be hard-linked files")
                identity = (info.st_dev, info.st_ino)
                if identity in source_ids or identity in destination_ids:
                    raise CliInputError(
                        "output paths cannot alias inputs or each other through hard links"
                    )
                destination_ids.add(identity)
            ancestor = canonical.parent
            while not ancestor.exists() and ancestor != ancestor.parent:
                ancestor = ancestor.parent
            if not ancestor.is_dir():
                raise CliInputError(f"output parent is not a directory: {ancestor}")

    def publish(self, payloads: dict[Path, bytes]) -> None:
        # Complete every serialization/write before replacing any public result.
        for target in self.targets:
            with self.staged[target].open("wb") as handle:
                handle.write(payloads[target])
                handle.flush()
                os.fsync(handle.fileno())
        for target in self.targets:
            os.replace(self.staged[target], self.resolved_targets[target])
            del self.staged[target]

    def _cleanup(self) -> None:
        for path in self.staged.values():
            path.unlink(missing_ok=True)
        self.staged.clear()

    def __exit__(self, *exception: object) -> None:
        self._cleanup()


def _path_key(path: Path) -> str:
    # Conservative on every filesystem: absent names may alias on macOS/Windows.
    return unicodedata.normalize("NFD", unicodedata.normalize("NFD", path.as_posix()).casefold())


def _validate(args: argparse.Namespace) -> int:
    bundle = RunBundle(args.run)
    baseline = RunBundle(args.baseline) if args.baseline is not None else None
    roots = [bundle.root, *([baseline.root] if baseline else [])]
    if any(not root.is_dir() for root in roots):
        raise CliInputError("candidate and baseline run roots must be existing directories")
    targets = [path for path in (args.json_out, args.md_out, args.junit_out) if path is not None]
    with _OutputBatch(targets, [args.spec], roots) as outputs:
        spec = load_spec(args.spec)
        if baseline is not None and not any(report.regressions for report in spec.reports):
            raise CliInputError("--baseline requires a contract declaring regressions")
        result = validate_run(bundle, spec, baseline=baseline, strict_warnings=args.strict_warnings)
        status_bytes = _json_object_bytes(result.to_dict())
        payloads = {}
        if args.json_out is not None:
            payloads[args.json_out] = status_bytes
        if args.md_out is not None:
            payloads[args.md_out] = render_review_packet(result).encode("utf-8")
        if args.junit_out is not None:
            payloads[args.junit_out] = render_junit_xml(result).encode("utf-8")
        outputs.publish(payloads)
    if args.json_out is None:
        sys.stdout.write(status_bytes.decode("utf-8"))
    return 0 if result.passed else 1


def _packet(args: argparse.Namespace) -> int:
    if not args.status.is_file():
        raise CliInputError("status input must be an existing regular file")
    with _OutputBatch([args.md_out], [args.status], []) as outputs:
        payload = parse_json(args.status.read_text(encoding="utf-8"))
        result = ValidationResult.from_dict(payload)
        outputs.publish({args.md_out: render_review_packet(result).encode("utf-8")})
    return 0


def _init_example(args: argparse.Namespace) -> int:
    source = resources.files("evidence_gate").joinpath("examples", args.name)
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
