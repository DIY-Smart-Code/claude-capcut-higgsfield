#!/usr/bin/env python3
"""virality_scores.py - pull the headline numbers out of a Higgsfield Virality Predictor result.

The predictor's result_url is a self-contained HTML dashboard (several MB). Its embedded JSON carries the
scores; this prints them and appends them to <work>/virality.json so before/after runs stay comparable.

  python virality_scores.py WORK <result_url or local .html> [--label "hook v2"]
"""
import argparse, datetime as dt, json, os, re, urllib.request

KEYS = ["hook_score", "viral_potential", "overall_score", "analysis_score", "sustain_score"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("source")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    if os.path.exists(a.source):
        html = open(a.source, encoding="utf-8", errors="ignore").read()
    else:
        req = urllib.request.Request(a.source, headers={"User-Agent": "capcut-higgsfield/1.0"})
        html = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "ignore")
    row = {"label": a.label, "source": a.source, "at": dt.datetime.now().isoformat(timespec="seconds")}
    for k in KEYS:
        m = re.search(r'"' + k + r'"\s*:\s*([0-9.]+)', html)
        row[k] = float(m.group(1)) if m else None
    p = os.path.join(a.work, "virality.json")
    hist = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    hist.append(row)
    json.dump(hist, open(p, "w", encoding="utf-8"), indent=1)
    for r in hist:
        print(f'{r["label"] or "-":<16} hook {r["hook_score"]!s:>5}  viral {r["viral_potential"]!s:>5}  '
              f'overall {r["overall_score"]!s:>5}  sustain {r["sustain_score"]!s:>9}')


if __name__ == "__main__":
    main()
