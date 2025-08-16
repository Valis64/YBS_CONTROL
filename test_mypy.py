import subprocess


def test_mypy() -> None:
    result = subprocess.run(
        ["mypy", "--ignore-missing-imports", "--follow-imports=skip", "ui/order_app.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
