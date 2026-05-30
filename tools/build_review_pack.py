#!/usr/bin/env python3
"""Build a synthetic executive portfolio review pack from CSV inputs.

This tool is intentionally simple, transparent, and standard-library only.
It does not call external APIs, change project plans, send messages, approve work,
change funding, accept risk, or alter live systems.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List

REQUIRED_COLUMNS = [
    "initiative_id", "initiative_name", "portfolio_area", "status", "sponsor", "owner", "stage", "priority",
    "update_date", "health", "summary", "decision_needed", "decision_request", "options", "risk", "blocker",
    "dependency", "capacity_pressure", "funding_constraint", "sponsor_action", "evidence", "next_review",
    "target_commitment", "handoff"
]

REVIEW_DATE = date(2026, 5, 29)


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"Missing required columns: {', '.join(missing)}")
        return [{k: (v or '').strip() for k, v in row.items()} for row in reader]


def days_old(value: str) -> int:
    try:
        return (REVIEW_DATE - datetime.strptime(value, "%Y-%m-%d").date()).days
    except Exception:
        return 999


def classify(row: Dict[str, str]) -> List[Dict[str, str]]:
    findings = []
    base = {
        "initiative_id": row["initiative_id"],
        "initiative_name": row["initiative_name"],
        "sponsor": row["sponsor"],
        "owner": row["owner"],
        "handoff": row["handoff"],
    }

    def add(kind: str, severity: str, finding: str, basis: str, suggested_action: str) -> None:
        item = dict(base)
        item.update({"kind": kind, "severity": severity, "finding": finding, "basis": basis, "suggested_action": suggested_action})
        findings.append(item)

    if row["decision_needed"].lower() == "yes" or row["decision_request"]:
        severity = "High" if not row["options"] else "Medium"
        action = "Prepare for executive discussion; human decision required."
        if not row["options"]:
            action = "Clarify options, owner, timing, and tradeoffs before treating as decision-ready."
        add("Decision Needed", severity, row["decision_request"] or "Decision request not stated", "Decision flag or request present", action)

    if row["status"].lower() == "stalled":
        add("Stalled Item", "High", "Item is stalled and needs disposition, owner confirmation, or closure decision.", row["summary"], "Route to PMO Governance Operations Log for follow-through.")

    if row["risk"]:
        add("Risk", "Medium", row["risk"], "Risk field populated", "Summarize impact, mitigation, owner, and escalation need.")
    if row["blocker"]:
        add("Blocker", "High", row["blocker"], "Blocker field populated", "Identify sponsor action or accountable path to unblock.")
    if row["dependency"]:
        add("Dependency", "Medium", row["dependency"], "Dependency field populated", "Assess sequencing impact and hand off if deeper capacity planning is needed.")
    if row["capacity_pressure"]:
        add("Capacity Pressure", "High", row["capacity_pressure"], "Capacity pressure field populated", "Review commitment risk and route sequencing question if needed.")
    if row["funding_constraint"]:
        add("Funding Constraint", "High", row["funding_constraint"], "Funding constraint field populated", "Frame as human-owned tradeoff; do not imply approval.")
    if row["sponsor_action"]:
        add("Sponsor Action", "High", row["sponsor_action"], "Sponsor action field populated", "Add to sponsor action register with owner and date.")

    weak_evidence = any(token in row["evidence"].lower() for token in ["weak", "missing", "stale", "verbal"])
    stale_update = days_old(row["update_date"]) > 14
    stale_green = row["health"].lower() == "green" and (weak_evidence or stale_update)
    if weak_evidence or stale_update or stale_green:
        label = "Stale green status" if stale_green else "Weak or stale signal"
        add("Signal Quality", "Medium", label, f"Evidence: {row['evidence']}; update age: {days_old(row['update_date'])} days", "Ask for refreshed evidence before relying on this signal.")

    if not findings:
        add("Routine Status", "Low", "Routine update; no executive action detected.", row["summary"], "Include only in summary rollup unless executive attention is requested.")
    return findings


def summarize(rows: List[Dict[str, str]], findings: List[Dict[str, str]]) -> Dict[str, int]:
    return {
        "total_records": len(rows),
        "active_initiatives": sum(1 for r in rows if r["status"].lower() == "active"),
        "stalled_items": sum(1 for r in rows if r["status"].lower() == "stalled"),
        "decision_requests": sum(1 for f in findings if f["kind"] == "Decision Needed"),
        "funding_constraints": sum(1 for f in findings if f["kind"] == "Funding Constraint"),
        "dependencies": sum(1 for f in findings if f["kind"] == "Dependency"),
        "capacity_pressures": sum(1 for f in findings if f["kind"] == "Capacity Pressure"),
        "sponsor_actions": sum(1 for f in findings if f["kind"] == "Sponsor Action"),
        "signal_quality_findings": sum(1 for f in findings if f["kind"] == "Signal Quality"),
        "high_severity_findings": sum(1 for f in findings if f["severity"] == "High"),
    }


def group_by_kind(findings: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for item in findings:
        grouped.setdefault(item["kind"], []).append(item)
    return grouped


def render_html(rows: List[Dict[str, str]], findings: List[Dict[str, str]]) -> str:
    s = summarize(rows, findings)
    grouped = group_by_kind(findings)
    cards = "".join(f"<div class='metric'><strong>{html.escape(k.replace('_',' ').title())}</strong><span>{v}</span></div>" for k, v in s.items())

    def table(items: List[Dict[str, str]]) -> str:
        if not items:
            return "<p>No findings.</p>"
        head = "<tr><th>Initiative</th><th>Severity</th><th>Finding</th><th>Suggested action</th><th>Handoff</th></tr>"
        body = "".join(
            f"<tr><td>{html.escape(i['initiative_name'])}</td><td>{html.escape(i['severity'])}</td><td>{html.escape(i['finding'])}</td><td>{html.escape(i['suggested_action'])}</td><td>{html.escape(i['handoff'])}</td></tr>"
            for i in items
        )
        return f"<table>{head}{body}</table>"

    sections = []
    order = ["Decision Needed", "Funding Constraint", "Capacity Pressure", "Dependency", "Blocker", "Risk", "Sponsor Action", "Signal Quality", "Stalled Item", "Routine Status"]
    for kind in order:
        if kind in grouped:
            sections.append(f"<h2>{html.escape(kind)}</h2>{table(grouped[kind])}")

    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>Executive Portfolio Review Pack</title>
<style>body{{font-family:Arial,sans-serif;margin:40px;line-height:1.5;color:#222}}h1,h2{{line-height:1.2}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:20px 0}}.metric{{border:1px solid #ddd;border-radius:8px;padding:12px;background:#fafafa}}.metric span{{display:block;font-size:28px;margin-top:6px}}table{{border-collapse:collapse;width:100%;font-size:14px;margin-bottom:24px}}th,td{{border:1px solid #ddd;padding:7px;text-align:left;vertical-align:top}}th{{background:#f4f4f4}}.callout{{border-left:5px solid #555;background:#f7f7f7;padding:12px;margin:16px 0}}.human{{background:#fff8e8;border:1px solid #ead9a8;padding:12px;border-radius:8px}}</style>
</head><body>
<h1>Executive Portfolio Review Pack</h1>
<p><strong>Review date:</strong> {REVIEW_DATE.isoformat()}</p>
<div class=\"callout\"><strong>Executive readout:</strong> The sample portfolio contains active delivery work, stalled items, executive decision requests, dependency pressure, funding constraints, and weak signal-quality evidence. The pack is designed to support sponsor discussion, not to make decisions autonomously.</div>
<div class=\"metrics\">{cards}</div>
<h2>Recommended executive agenda</h2>
<ol><li>Confirm decision requests that are ready for discussion.</li><li>Review Data Platform dependency and downstream commitment risk.</li><li>Resolve funding and capacity constraints before confirming Q3 commitments.</li><li>Decide disposition path for stalled work.</li><li>Assign follow-up capture to PMO Governance Operations Log.</li></ol>
{''.join(sections)}
<div class=\"human\"><strong>Human-control reminder:</strong> This output identifies candidate decisions, risks, constraints, and handoffs. It does not approve funding, accept risk, reprioritize work, change sequencing, or assign owners.</div>
</body></html>"""


def write_findings_csv(path: Path, findings: List[Dict[str, str]]) -> None:
    if not findings:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(findings[0].keys()))
        writer.writeheader(); writer.writerows(findings)


def write_findings_jsonl(path: Path, findings: List[Dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in findings:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a synthetic executive portfolio review pack.")
    parser.add_argument("--input", default="examples/sample-data.csv")
    parser.add_argument("--output", default="examples/sample-output.html")
    parser.add_argument("--findings-csv", default="examples/findings-log.csv")
    parser.add_argument("--findings-jsonl", default="examples/findings-log.jsonl")
    args = parser.parse_args()

    rows = load_rows(Path(args.input))
    findings = []
    for row in rows:
        findings.extend(classify(row))

    Path(args.output).write_text(render_html(rows, findings), encoding="utf-8")
    write_findings_csv(Path(args.findings_csv), findings)
    write_findings_jsonl(Path(args.findings_jsonl), findings)
    print(json.dumps(summarize(rows, findings), indent=2))


if __name__ == "__main__":
    main()
