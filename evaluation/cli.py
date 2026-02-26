"""CLI entry point: python -m evaluation.cli <benchmark> [--phase <phase>]."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NeuroMemory Benchmark Evaluation",
        prog="python -m evaluation.cli",
    )
    parser.add_argument(
        "benchmark",
        choices=["locomo", "longmemeval"],
        help="Which benchmark to run",
    )
    parser.add_argument(
        "--phase",
        choices=["ingest", "query", "evaluate"],
        default=None,
        help="Run a specific phase only (default: all phases)",
    )
    parser.add_argument(
        "--conv",
        type=int,
        default=None,
        help="Run only a specific conversation index (e.g. --conv 0)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only first N questions/conversations",
    )
    # Parallelism overrides (take precedence over env vars)
    parser.add_argument(
        "--ingest-concurrency",
        type=int, default=None,
        help="Max concurrent conversation ingestions (default: 2)",
    )
    parser.add_argument(
        "--query-concurrency",
        type=int, default=None,
        help="Max concurrent query tasks (default: 5)",
    )
    parser.add_argument(
        "--evaluate-concurrency",
        type=int, default=None,
        help="Max concurrent judge evaluations (default: 10)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from evaluation.config import EvalConfig
    cfg = EvalConfig()

    # CLI overrides for concurrency
    if args.ingest_concurrency is not None:
        cfg.ingest_concurrency = args.ingest_concurrency
    if args.query_concurrency is not None:
        cfg.query_concurrency = args.query_concurrency
    if args.evaluate_concurrency is not None:
        cfg.evaluate_concurrency = args.evaluate_concurrency

    if args.benchmark == "locomo":
        from evaluation.pipelines.locomo import run_locomo
        asyncio.run(run_locomo(cfg, phase=args.phase, conv_filter=args.conv))
    elif args.benchmark == "longmemeval":
        from evaluation.pipelines.longmemeval import run_longmemeval
        asyncio.run(run_longmemeval(cfg, phase=args.phase))


if __name__ == "__main__":
    main()
