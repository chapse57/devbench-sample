import argparse
import json

from . import collect, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metricsd")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="CSV(account,followers)를 한 번의 실행으로 기록하고 run_id를 출력")
    p_collect.add_argument("--input", required=True)

    sub.add_parser("runs", help="기록된 실행 목록(오래된 것 → 최신 순)을 JSON으로 출력")

    p_show = sub.add_parser("show", help="한 실행의 측정값을 JSON으로 출력")
    p_show.add_argument("run_id")

    sub.add_parser("diff", help="최신 실행과 직전 실행의 차이를 JSON으로 출력")

    args = parser.parse_args(argv)

    if args.command == "collect":
        print(collect.collect(args.input))
    elif args.command == "runs":
        print(json.dumps(report.list_runs(), ensure_ascii=False))
    elif args.command == "show":
        print(json.dumps(report.show(args.run_id), ensure_ascii=False))
    elif args.command == "diff":
        print(json.dumps(report.diff(), ensure_ascii=False))
    return 0
