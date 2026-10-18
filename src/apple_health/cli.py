"""Command-line entry point: ``uv run apple-health <command>``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from apple_health import __version__
from apple_health.config import Config, load_config

log = logging.getLogger("apple_health")


def _config(args: argparse.Namespace) -> Config:
    cfg = load_config(args.config_dir)
    return cfg.with_paths(raw_dir=args.raw_dir, warehouse_dir=args.warehouse_dir)


def cmd_parse(cfg: Config, args: argparse.Namespace) -> int:
    from apple_health.pipeline import run_parse

    return run_parse(cfg)


def cmd_build(cfg: Config, args: argparse.Namespace) -> int:
    from apple_health.build import run_build

    return run_build(cfg)


def cmd_check(cfg: Config, args: argparse.Namespace) -> int:
    from apple_health.build import run_check

    return run_check(cfg)


def cmd_diff(cfg: Config, args: argparse.Namespace) -> int:
    from apple_health.quality.profile import run_diff

    return run_diff(cfg.settings.warehouse_dir)


def cmd_dictionary(cfg: Config, args: argparse.Namespace) -> int:
    from apple_health.docs import write_data_dictionary

    path = write_data_dictionary(cfg, args.output)
    log.info("wrote %s", path)
    return 0


def cmd_all(cfg: Config, args: argparse.Namespace) -> int:
    for step in (cmd_parse, cmd_build, cmd_diff):
        rc = step(cfg, args)
        if rc:
            return rc
    return 0


COMMANDS = {
    "parse": (cmd_parse, "raw export -> staging Parquet"),
    "build": (cmd_build, "staging -> curated + derived Parquet, with data-quality checks"),
    "check": (cmd_check, "re-run data-quality checks on the published warehouse"),
    "diff": (cmd_diff, "compare the latest two export profiles (drift report)"),
    "all": (cmd_all, "parse + build + diff"),
    "dictionary": (cmd_dictionary, "regenerate docs/data_dictionary.md from the table definitions"),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apple-health", description=__doc__)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config-dir", type=Path, default=None, help="directory with settings.toml etc.")
    p.add_argument("--raw-dir", type=Path, default=None, help="override paths.raw_dir")
    p.add_argument("--warehouse-dir", type=Path, default=None, help="override paths.warehouse_dir")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    for name, (_, help_) in COMMANDS.items():
        sp = sub.add_parser(name, help=help_)
        if name == "dictionary":
            sp.add_argument("--output", type=Path, default=Path("docs/data_dictionary.md"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = _config(args)
    fn, _ = COMMANDS[args.command]
    return fn(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
