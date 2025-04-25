import pytest
from click.testing import CliRunner

import catherd.cli

MAX_OUTPUT_LINES = 32


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Limit captured output per test."""
    # Only modify output for the call phase (i.e. test execution)
    if report.when == "call" and report.failed:
        new_sections: list[tuple[str, str]] = []
        for title, content in report.sections:
            if title.startswith(("Captured stdout", "Captured stderr")):
                lines = content.splitlines()
                if len(lines) > MAX_OUTPUT_LINES:
                    truncated_section: str = "\n".join(*[lines[:MAX_OUTPUT_LINES], "... [output truncated]"])
                    new_sections.append((title, truncated_section))
                else:
                    new_sections.append((title, content))

            else:
                new_sections.append((title, content))
        report.sections = new_sections


@pytest.fixture
def runner():
    runner = CliRunner()
    orig = runner.invoke

    def invoke(cli=None, args=None, **kwargs):
        # if called as runner.invoke(["-m", "catherd"]), strip the "-m catherd"
        if isinstance(cli, (list, tuple)):
            arr = list(cli)
            if len(arr) >= 2 and arr[0] == "-m" and arr[1] == "catherd":
                return orig(catherd.cli.main, [], **kwargs)
            # otherwise treat the list as args to main
            return orig(catherd.cli.main, arr, **kwargs)

        # default: use the passed-in command or main()
        cmd = cli or catherd.cli.main
        return orig(cmd, args or [], **kwargs)

    runner.invoke = invoke
    return runner
