"""Build a markdown report comparing coverage before and after a PR."""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MARKER = "<!-- coverage-report -->"


def load(path: str) -> dict[str, float] | None:  # numpydoc ignore=PR01
    """Return {file: percent} plus a "TOTAL" key, or None if the report is missing."""
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    files = {f: d["summary"]["percent_covered"] for f, d in data["files"].items()}
    files["TOTAL"] = data["totals"]["percent_covered"]
    return files


def load_duration(path: str) -> float | None:  # numpydoc ignore=PR01
    """Return the total test duration in seconds from a JUnit XML report, or None."""
    p = Path(path)
    if not p.exists():
        return None
    root = ET.parse(p).getroot()
    suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
    return sum(float(s.get("time", 0)) for s in suites)


def fmt_duration(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}s"


def delta_duration(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return ""
    diff = after - before
    if abs(diff) < 0.05:
        return "="
    return f"{'🔴 +' if diff > 0 else '🟢 '}{diff:.1f}s"


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def delta(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return ""
    diff = after - before
    if abs(diff) < 0.005:
        return "="
    return f"{'🟢 +' if diff > 0 else '🔴 '}{diff:.2f}"


def main(base_path: str, head_path: str, base_junit: str, head_junit: str) -> str:
    base, head = load(base_path), load(head_path)
    base_time, head_time = load_duration(base_junit), load_duration(head_junit)
    lines = [MARKER, "## Tests report", ""]

    if head is None:
        lines.append(
            "Coverage could not be computed for this PR (see the workflow logs)."
        )
        return "\n".join(lines)

    base_total = None if base is None else base["TOTAL"]
    lines += [
        "| | Before (base) | After (PR) | Change |",
        "|---|---:|---:|---:|",
        f"| **Coverage** | {fmt(base_total)} | {fmt(head['TOTAL'])} "
        f"| {delta(base_total, head['TOTAL'])} |",
        f"| **Test duration** | {fmt_duration(base_time)} | {fmt_duration(head_time)} "
        f"| {delta_duration(base_time, head_time)} |",
        "",
    ]

    if base is None:
        lines.append("_The base branch could not be measured._")
        return "\n".join(lines)

    rows = []
    for name in sorted((base.keys() | head.keys()) - {"TOTAL"}):
        before, after = base.get(name), head.get(name)
        if before is None or after is None or abs(after - before) >= 0.005:
            rows.append(
                f"| `{name}` | {fmt(before)} | {fmt(after)} | {delta(before, after)} |"
            )

    if rows:
        lines += [
            "<details><summary>Files with a coverage change</summary>",
            "",
            "| File | Before | After | Change |",
            "|---|---:|---:|---:|",
            *rows,
            "",
            "</details>",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(main(*sys.argv[1:5]))
