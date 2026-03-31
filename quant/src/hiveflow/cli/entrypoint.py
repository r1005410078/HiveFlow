import argparse
import json

from hiveflow.pipeline.application.daily_run_use_case import run_daily_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="hf")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("pipeline")
    psub = p.add_subparsers(dest="sub")
    d = psub.add_parser("daily")
    d.add_argument("--as-of", required=True)

    args = parser.parse_args()

    if args.cmd == "pipeline" and args.sub == "daily":
        payload = run_daily_pipeline(as_of=args.as_of, root="data")
        print(json.dumps(payload, ensure_ascii=False))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
