"""Two additional cases reserved until after freezing the classification and pricing code."""
import argparse
import hashlib
import json
from run import ROOT, CLASSIFY, candidates, classify_charges, infer, ledger, read_json, score, validate, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--endpoint", default="http://127.0.0.1:18973")
    args = parser.parse_args()
    output = ROOT/"fresh"
    output.mkdir(exist_ok=True)
    results = []
    for case in read_json(ROOT/"fresh-cases.json"):
        model_input = {"situation":case["scenario"],"notice":case["lines"],"candidates":candidates(case)}
        path = output/(case["id"]+".json")
        if not args.replay:
            write_json(path, infer(args.endpoint, CLASSIFY, json.dumps(model_input,ensure_ascii=False), 520))
        response = read_json(path)
        record = {"id":case["id"]}
        try:
            if response["finish_reason"] != "stop":
                raise ValueError("模型回复不完整")
            choices = classify_charges(case,json.loads(response["content"]))
            charges = validate(case, {"charges":choices})
            record["totals"] = ledger(case, charges)
            record["matched"] = False if case["expected"].get("review") else score(charges,case["expected"],record["totals"])["all_exact"]
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            record["review"] = str(exc)
            record["matched"] = case["expected"].get("review",False)
        results.append(record)
    write_json(output/"results.json",{"run_sha256":hashlib.sha256((ROOT/"run.py").read_bytes()).hexdigest(),"cases":results})
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
