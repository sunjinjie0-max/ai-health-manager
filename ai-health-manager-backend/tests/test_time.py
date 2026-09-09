from datetime import datetime, timezone

from app.core.time import as_utc_aware, utc_isoformat, utc_now, utc_now_naive


def test_utc_now_is_timezone_aware():
    value = utc_now()
    assert value.tzinfo is not None
    assert value.utcoffset() == timezone.utc.utcoffset(value)


def test_utc_now_naive_has_no_timezone():
    value = utc_now_naive()
    assert value.tzinfo is None


def test_as_utc_aware_coerces_naive_datetime():
    value = as_utc_aware(datetime(2026, 5, 3, 12, 0, 0))
    assert value.tzinfo is not None
    assert value.isoformat().endswith("+00:00")


def test_utc_isoformat_uses_z_suffix():
    value = utc_isoformat(datetime(2026, 5, 3, 12, 0, 0))
    assert value.endswith("Z")
