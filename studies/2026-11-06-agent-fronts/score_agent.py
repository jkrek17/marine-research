"""Collect the agent's answer.json files from the blind folders, score them with the drill's scorer.
  python3 score_agent.py <blind_dir>   -> agent_answers.json (the fronts and reasons), agent_test.csv
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

import common
import deck

HERE = common.HERE


def main(blind):
    ids = deck.test_ids()
    man = deck.manifest()
    basin = {c["id"]: c["basin"] for c in man["cases"]}
    answers, drawn = {}, {}
    for i in ids:
        a = json.loads((Path(blind) / i / "answer.json").read_text())
        fr = [f for f in a.get("fronts", []) if f.get("type") in deck.DRAWN and len(f.get("pts", [])) >= 2]
        for f in fr:
            f["pts"] = [[float(p[0]), float(p[1]) % 360] for p in f["pts"]]
        answers[i] = {"fronts": fr, "note": a.get("note", "")}
        drawn[i] = [{"type": f["type"], "pts": f["pts"]} for f in fr]
    (HERE / "agent_answers.json").write_text(json.dumps(answers, indent=0))
    sc = common.score(drawn)
    with open(HERE / "agent_test.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "basin", "pct", "n_truth", "n_matched", "n_type_right", "extras"])
        for i in ids:
            r = sc[i]
            w.writerow([i, basin[i], round(r["pct"], 1), len(r["rows"]), sum(x["matched"] for x in r["rows"]),
                        sum(x["matched"] and x["drawnType"] == x["type"] for x in r["rows"]), r["extras"]])
    print("agent test mean", round(float(np.mean([sc[i]["pct"] for i in ids])), 1))


if __name__ == "__main__":
    main(sys.argv[1])
