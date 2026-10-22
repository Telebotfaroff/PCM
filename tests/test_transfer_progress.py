from pcm.bot.progress import TransferProgress, format_bytes, format_duration


def test_format_bytes_uses_binary_units():
    assert format_bytes(1024) == "1.00 KiB"
    assert format_bytes(1024 * 1024) == "1.00 MiB"


def test_format_duration_is_compact():
    assert format_duration(7) == "7s"
    assert format_duration(75) == "1m 15s"
    assert format_duration(3660) == "1h 01m"


def test_progress_renders_bar_and_transfer_details():
    meter = TransferProgress("Example episode", "📥 Downloading", quality="720p")
    message = meter.render(50, 100, force=True)
    assert message is not None
    assert "📥 Downloading" in message
    assert "Example episode" in message
    assert "720p" in message
    assert "50.0%" in message
    assert "50.0 B / 100.0 B" in message


def test_progress_can_report_unknown_total():
    meter = TransferProgress("Example", "📤 Uploading")
    message = meter.render(1024 * 1024, 0, force=True)
    assert message is not None
    assert "1.00 MiB transferred" in message
    assert "%" not in message


def test_progress_throttles_repeated_updates():
    meter = TransferProgress("Example", "📥 Downloading", interval=60)
    assert meter.render(1, 100, force=True) is not None
    assert meter.render(2, 100) is None
