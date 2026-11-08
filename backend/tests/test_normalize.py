import pytest

from kensa.ingestion.normalize import (
    MAX_LINE_CHARS,
    MAX_LINES,
    MAX_LOG_BYTES,
    LogRejectedError,
    normalize_log,
    strip_timestamp,
)


def test_strips_ansi_control_chars_and_crlf() -> None:
    raw = "\x1b[31mred\x1b[0m line\r\nbell\x07 and \x00null\r\nprogress\r100%\n"
    result = normalize_log(raw)
    assert result.text == "red line\nbell and null\nprogress\n100%"
    assert result.line_count == 4


def test_long_lines_are_truncated_but_kept() -> None:
    result = normalize_log("a" * (MAX_LINE_CHARS + 50) + "\nnext")
    first, second = result.text.split("\n")
    assert first.endswith("…[truncated]")
    assert len(first) < MAX_LINE_CHARS + 50
    assert second == "next"
    assert result.truncated_lines == 1


@pytest.mark.parametrize(
    "raw",
    ["", "\n\n   \n", "x" * (MAX_LOG_BYTES + 1), "\n".join(["x"] * (MAX_LINES + 1))],
)
def test_rejects_empty_or_oversized_input(raw: str) -> None:
    with pytest.raises(LogRejectedError):
        normalize_log(raw)


def test_strip_timestamp() -> None:
    assert strip_timestamp("2026-10-01T10:00:20.8000000Z Error: boom") == "Error: boom"
    assert strip_timestamp("no timestamp here") == "no timestamp here"
