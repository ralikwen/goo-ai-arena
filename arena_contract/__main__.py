"""Local CLI. Validation is read-only; fixtures are created only on explicit request."""

import argparse
import json

from .validator import validate_bundle


def main():
    parser = argparse.ArgumentParser(description="Goo AI Arena local contract trial; no publication or native execution")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="Check one data bundle without publishing it")
    check.add_argument("bundle")
    check.add_argument("--ruleset", action="append", default=[], help="Additional exact local ruleset JSON; repeatable")
    check.add_argument("--reference", action="append", default=[], help="Referenced bundle directory or manifest; repeatable")
    check.add_argument("--allow-demo", action="store_true", help="TEST ONLY: permit explicitly synthetic fixtures")
    fixtures = commands.add_parser("fixtures", help="Create synthetic fixtures in a new directory; never overwrite")
    fixtures.add_argument("destination")
    args = parser.parse_args()
    if args.command == "fixtures":
        from .fixtures import build_trial
        try:
            index = build_trial(args.destination)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(index, indent=2))
        return 0
    result = validate_bundle(args.bundle, allow_demo=args.allow_demo,
                             rulesets=args.ruleset, references=args.reference)
    print(json.dumps(result, indent=2))
    return {"admitted": 0, "needs_correction": 1, "pending": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
