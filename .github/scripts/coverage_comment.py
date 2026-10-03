"""
Build a markdown report comparing coverage and test duration before and after a PR.

Both arguments are directories holding one ``results-<python version>`` folder per
tested Python version, each with a ``junit.xml`` (and, for one of them, a
``coverage.json``).
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MARKER = "<!-- coverage-report -->"


def version_key(version: str) -> tuple:  # numpydoc ignore=PR01,RT01
    """Sort key so that 3.9 comes before 3.10."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (float("inf"), version)


def load_coverage(results: Path) -> dict[str, float] | None:  # numpydoc ignore=PR01
    """Return {file: percent} plus a "TOTAL" key, or None if there is no report."""
    paths = sorted(results.glob("*/coverage.json"))
    if not paths:
        return None
    data = json.loads(paths[0].read_text(encoding="utf-8"))
    files = {f: d["summary"]["percent_covered"] for f, d in data["files"].items()}
    files["TOTAL"] = data["totals"]["percent_covered"]
    return files


def load_durations(results: Path) -> dict[str, float]:  # numpydoc ignore=PR01
    """Return {python version: total test duration in seconds} from the JUnit reports."""
    durations = {}
    for junit in results.glob("results-*/junit.xml"):
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
        version = junit.parent.name.removeprefix("results-")
        durations[version] = sum(float(s.get("time", 0)) for s in suites)
    return durations


def fmt(value: float | None) -> str:  # numpydoc ignore=PR01,RT01
    """Format a coverage percentage."""
    return "n/a" if value is None else f"{value:.2f}%"


def delta(
    before: float | None, after: float | None
) -> str:  # numpydoc ignore=PR01,RT01
    """Format a coverage variation with a marker."""
    if before is None or after is None:
        return ""
    diff = after - before
    if abs(diff) < 0.005:
        return "="
    return f"{'🟢 +' if diff > 0 else '🔴 '}{diff:.2f}"


def fmt_duration(value: float | None) -> str:  # numpydoc ignore=PR01,RT01
    """Format a duration in seconds."""
    return "n/a" if value is None else f"{value:.2f}s"


def delta_duration(
    before: float | None, after: float | None
) -> str:  # numpydoc ignore=PR01,RT01
    """Format a duration variation with a marker (red is slower)."""
    if before is None or after is None:
        return ""
    diff = after - before
    if abs(diff) < 0.05:
        return "="
    return f"{'🔴 +' if diff > 0 else '🟢 '}{diff:.1f}s"


def mean(values: list[float]) -> float | None:  # numpydoc ignore=PR01,RT01
    """Return the mean of values, or None if there are none."""
    return sum(values) / len(values) if values else None


def duration_summary(
    base_times: dict[str, float], head_times: dict[str, float]
) -> tuple[str, float | None, float | None]:  # numpydoc ignore=PR01,RT01
    """Return the label and the before/after mean durations of the summary row."""
    # Only versions measured on both sides are comparable.
    common = sorted(base_times.keys() & head_times.keys(), key=version_key)
    if not common:
        return "Test duration", None, mean(list(head_times.values()))

    if len(common) > 1:
        label = f"Test duration (mean of {len(common)} versions)"
    else:
        label = f"Test duration (Python {common[0]})"
    return (
        label,
        mean([base_times[v] for v in common]),
        mean([head_times[v] for v in common]),
    )


def summary_table(
    base: dict[str, float] | None,
    head: dict[str, float],
    base_times: dict[str, float],
    head_times: dict[str, float],
) -> list[str]:  # numpydoc ignore=PR01,RT01
    """Return the Before/After table with the total coverage and test duration."""
    label, base_mean, head_mean = duration_summary(base_times, head_times)
    base_total = None if base is None else base["TOTAL"]
    return [
        "| | Before | After | Change |",
        "|---|---:|---:|---:|",
        f"| **Coverage** | {fmt(base_total)} | {fmt(head['TOTAL'])} "
        f"| {delta(base_total, head['TOTAL'])} |",
        f"| **{label}** | {fmt_duration(base_mean)} | {fmt_duration(head_mean)} "
        f"| {delta_duration(base_mean, head_mean)} |",
        "",
    ]


def duration_details(
    base_times: dict[str, float], head_times: dict[str, float]
) -> list[str]:  # numpydoc ignore=PR01,RT01
    """Return the collapsible per-Python-version duration table."""
    rows = []
    for version in sorted(head_times, key=version_key):
        before, after = base_times.get(version), head_times[version]
        rows.append(
            f"| {version} | {fmt_duration(before)} | {fmt_duration(after)} "
            f"| {delta_duration(before, after)} |"
        )
    return details(
        "Test duration per Python version",
        ["| Python | Before | After | Change |", "|---|---:|---:|---:|", *rows],
    )


def coverage_details(
    base: dict[str, float] | None, head: dict[str, float]
) -> list[str]:  # numpydoc ignore=PR01,RT01
    """Return the collapsible table of files whose coverage changed."""
    if base is None:
        return ["_The baseline could not be measured._", ""]

    rows = []
    for name in sorted((base.keys() | head.keys()) - {"TOTAL"}):
        before, after = base.get(name), head.get(name)
        if before is None or after is None or abs(after - before) >= 0.005:
            rows.append(
                f"| `{name}` | {fmt(before)} | {fmt(after)} | {delta(before, after)} |"
            )
    if not rows:
        return []
    return details(
        "Files with a coverage change",
        ["| File | Before | After | Change |", "|---|---:|---:|---:|", *rows],
    )


def details(summary: str, body: list[str]) -> list[str]:  # numpydoc ignore=PR01,RT01
    """Wrap lines in a collapsible markdown section."""
    return [f"<details><summary>{summary}</summary>", "", *body, "", "</details>", ""]


def main(base_dir: str, head_dir: str) -> str:  # numpydoc ignore=PR01,RT01
    """Return the markdown report."""
    base_results, head_results = Path(base_dir), Path(head_dir)
    base, head = load_coverage(base_results), load_coverage(head_results)
    base_times, head_times = load_durations(base_results), load_durations(head_results)
    lines = [MARKER, "## Tests report", ""]

    if head is None:
        lines.append(
            "Coverage could not be computed for this PR (see the workflow logs)."
        )
        return "\n".join(lines)

    lines += summary_table(base, head, base_times, head_times)
    if head_times:
        lines += duration_details(base_times, head_times)
    lines += coverage_details(base, head)

    if note := os.environ.get("BASELINE_NOTE"):
        lines.append(f"<sub>{note}</sub>")
    return "\n".join(lines)


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2]))
