"""
main.py
~~~~~~~
Entry point for the colectatron8000 volunteer shift scheduler.

Usage
-----
python src/main.py \\
    --availability  data/availability.csv \\
    --capacities    data/capacities.csv \\
    --output        data/assignments.csv \\
    [--limits       data/volunteer_limits.csv] \\
    [--min-shifts   1] \\
    [--max-shifts   3] \\
    [--time-limit   300] \\
    [--mip-gap      0.01]
"""

from __future__ import annotations

import argparse
import pathlib
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "colectatron8000 – assign volunteers to fundraising collection shifts "
            "using an integer-programming model (Gurobi)."
        )
    )
    parser.add_argument(
        "--availability",
        required=True,
        metavar="FILE",
        help="Path to the volunteer availability CSV or Excel file.",
    )
    parser.add_argument(
        "--capacities",
        required=True,
        metavar="FILE",
        help="Path to the location capacities CSV or Excel file.",
    )
    parser.add_argument(
        "--output",
        default="data/assignments.csv",
        metavar="FILE",
        help="Path for the output assignments CSV (default: data/assignments.csv).",
    )
    parser.add_argument(
        "--limits",
        default=None,
        metavar="FILE",
        help="Optional path to a per-volunteer shift limits CSV or Excel file.",
    )
    parser.add_argument(
        "--min-shifts",
        type=int,
        default=1,
        metavar="N",
        help="Default minimum number of shifts per volunteer (default: 1).",
    )
    parser.add_argument(
        "--max-shifts",
        type=int,
        default=3,
        metavar="N",
        help="Default maximum number of shifts per volunteer (default: 3).",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=300.0,
        metavar="SECS",
        help="Gurobi solver time limit in seconds (default: 300).",
    )
    parser.add_argument(
        "--mip-gap",
        type=float,
        default=0.01,
        metavar="GAP",
        help="Relative MIP optimality gap tolerance (default: 0.01).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Lazy imports so argument errors are reported before heavy imports
    from data_processing import build_problem_data  # noqa: PLC0415
    from solver import build_and_solve  # noqa: PLC0415

    print("=== colectatron8000 ===")
    print(f"Availability : {args.availability}")
    print(f"Capacities   : {args.capacities}")
    print(f"Limits       : {args.limits or '(none – using defaults)'}")
    print(f"Min shifts   : {args.min_shifts}")
    print(f"Max shifts   : {args.max_shifts}")
    print()

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    print("Loading data...")
    problem = build_problem_data(
        availability_path=args.availability,
        capacities_path=args.capacities,
        limits_path=args.limits,
        default_min_shifts=args.min_shifts,
        default_max_shifts=args.max_shifts,
    )

    print(f"  Volunteers : {len(problem['volunteers'])}")
    print(f"  Blocks     : {len(problem['blocks'])}")

    # ------------------------------------------------------------------
    # 2. Solve
    # ------------------------------------------------------------------
    print("\nSolving...")
    assignments = build_and_solve(
        availability=problem["availability"],
        capacities=problem["capacities"],
        volunteers=problem["volunteers"],
        blocks=problem["blocks"],
        volunteer_min=problem["volunteer_min"],
        volunteer_max=problem["volunteer_max"],
        time_limit=args.time_limit,
        mip_gap=args.mip_gap,
    )

    if assignments.empty:
        print("\nNo assignments produced – check solver output above.")
        return 1

    # ------------------------------------------------------------------
    # 3. Export
    # ------------------------------------------------------------------
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(output_path, index=False)

    print(f"\nAssignments written to: {output_path}")
    print(f"Total shifts assigned : {len(assignments)}")
    print("\nSample output (first 10 rows):")
    print(assignments.head(10).to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
