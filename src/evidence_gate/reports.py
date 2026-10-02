from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from evidence_gate.models import ValidationResult
from evidence_gate.producers import _json_object_bytes, _write_atomic_bytes, write_report_atomic


def _validated(result: ValidationResult) -> ValidationResult:
    if not isinstance(result, ValidationResult):
        raise ValueError("expected a ValidationResult")
    payload = result.to_dict()
    _json_object_bytes(payload)
    return ValidationResult.from_dict(payload)


def write_status_json(result: ValidationResult, path: str | Path) -> Path:
    return write_report_atomic(path, _validated(result).to_dict())


def write_review_packet(result: ValidationResult, output_dir: Path, markdown: bool = True) -> Path:
    """Compatibility helper writing a review packet under an output directory."""
    path = output_dir / ("review-packet.md" if markdown else "review-packet.json")
    return write_review_packet_file(result, path, markdown=markdown)


def write_review_packet_file(
    result: ValidationResult, path: str | Path, markdown: bool = True
) -> Path:
    """Write a validated review packet to an explicit path with atomic replacement."""
    if not markdown:
        return write_status_json(result, path)
    return _write_atomic_bytes(path, render_review_packet(result).encode("utf-8"))


def render_review_packet(result: ValidationResult) -> str:
    """Render a Markdown packet with producer text escaped and bounded."""
    return to_markdown(result)


def _text(value: Any, limit: int = 1200) -> str:
    text = str(value)
    text = "".join(character if character.isprintable() else " " for character in text)
    if len(text) > limit:
        text = text[:limit] + "… [truncated]"
    text = html.escape(text, quote=True)
    return re.sub(r"([\\`*_{}\[\]()#!|~])", r"\\\1", text)


def _details(check_details: dict[str, Any] | None) -> list[str]:
    if not check_details:
        return []
    lines = ["", "| Detail | Value |", "| --- | --- |"]
    for key, value in sorted(check_details.items())[:12]:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        lines.append(f"| {_text(key, 100)} | {_text(rendered, 500)} |")
    if len(check_details) > 12:
        lines.append(
            "| Additional details | Omitted from this compact view; retained in JSON/JUnit. |"
        )
    return [*lines, ""]


def to_markdown(result: ValidationResult) -> str:
    result = _validated(result)
    lines = [
        "# Evidence Review Packet",
        "",
        f"Schema version: {result.schema_version}",
        f"Decision: {result.recommendation}",
        f"Run: {_text(result.run_root)}",
        "",
        "## Counts",
        "",
    ]
    for key in ("passed", "warnings", "failed", "total"):
        lines.append(f"- {key}: {result.counts[key]}")
    lines.extend(["", "## Checks", ""])
    for check in result.checks:
        path = f"; path={_text(check.path)}" if check.path else ""
        report = f"; report={_text(check.report)}" if check.report else ""
        lines.append(
            f"- **{check.severity}** {_text(check.code)}{report}{path}: {_text(check.message)}"
        )
        lines.extend(_details(check.details))
    return "\n".join(lines) + "\n"


def _xml_text(value: str) -> str:
    """Replace characters excluded by XML 1.0, preserving valid Unicode text."""
    return "".join(
        character
        if (
            ord(character) in (9, 10, 13)
            or 0x20 <= ord(character) <= 0xD7FF
            or 0xE000 <= ord(character) <= 0xFFFD
            or 0x10000 <= ord(character) <= 0x10FFFF
        )
        else "\ufffd"
        for character in value
    )


def render_junit_xml(result: ValidationResult) -> str:
    """Represent each evidence check as a testcase; warnings are skipped checks."""
    result = _validated(result)
    counts = result.counts
    totals = {
        "tests": str(counts["total"]),
        "failures": str(counts["failed"]),
        "skipped": str(counts["warnings"]),
        "errors": "0",
    }
    document = ET.Element("testsuites", totals)
    suite = ET.SubElement(document, "testsuite", {"name": "evidence-gate", **totals})
    for index, check in enumerate(result.checks, start=1):
        attributes = {
            "name": _xml_text(f"{index:04d}: {check.code}"),
            "classname": _xml_text(check.report or "evidence-gate"),
        }
        if check.path is not None:
            attributes["file"] = _xml_text(check.path)
        case = ET.SubElement(suite, "testcase", attributes)
        properties = ET.SubElement(case, "properties")
        for name, value in (
            ("code", check.code),
            ("severity", check.severity),
            ("report", check.report),
            ("path", check.path),
        ):
            if value is not None:
                ET.SubElement(properties, "property", {"name": name, "value": _xml_text(value)})
        detail_text = ""
        if check.details is not None:
            detail_text = json.dumps(
                check.details, sort_keys=True, ensure_ascii=False, allow_nan=False
            )
            ET.SubElement(
                properties, "property", {"name": "details", "value": _xml_text(detail_text)}
            )
        message = _xml_text(check.message)
        content = message + ("\nDetails: " + _xml_text(detail_text) if detail_text else "")
        if check.severity == "failure":
            ET.SubElement(
                case, "failure", {"type": _xml_text(check.code), "message": message}
            ).text = content
        elif check.severity == "warning":
            ET.SubElement(case, "skipped", {"message": message}).text = content
        ET.SubElement(case, "system-out").text = content
    ET.indent(document, space="  ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + ET.tostring(document, encoding="unicode")
        + "\n"
    )


def write_junit_xml(result: ValidationResult, path: str | Path) -> Path:
    return _write_atomic_bytes(path, render_junit_xml(result).encode("utf-8"))
