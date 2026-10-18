from __future__ import annotations

import pytest

from apple_health.cli import build_parser


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    for cmd in ("parse", "build", "check", "diff", "all"):
        assert cmd in out


def test_cli_all_check_diff_on_fixture(fixture_export, tmp_path):
    from apple_health.cli import main

    args = ["--raw-dir", str(fixture_export), "--warehouse-dir", str(tmp_path / "wh")]
    assert main([*args, "all"]) == 0
    assert main([*args, "check"]) == 0
    assert main([*args, "diff"]) == 0
    assert (tmp_path / "wh" / "derived" / "agg_quantity_daily.parquet").is_file()


def test_cli_build_without_staging(tmp_path, fixture_export):
    from apple_health.cli import main

    assert main(["--raw-dir", str(fixture_export), "--warehouse-dir", str(tmp_path / "wh"), "build"]) == 2
    assert main(["--warehouse-dir", str(tmp_path / "wh"), "check"]) == 2
