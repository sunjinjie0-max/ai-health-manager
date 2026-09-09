#!/usr/bin/env python3
"""Debug script to test date parsing logic."""

import re
from datetime import date, timedelta

# Mock today as 2026-06-10
TODAY = date(2026, 6, 10)

def _target_date_from_message(message: str, today_override: date = None) -> date:
    """Test version of the date parsing function."""
    today = today_override or TODAY
    print(f"  Today: {today}")
    print(f"  Input message: '{message}'")
    
    # Check for relative dates
    if "明天" in message:
        result = today + timedelta(days=1)
        print(f"  ✓ Matched '明天' → {result}")
        return result
    if "昨天" in message:
        result = today - timedelta(days=1)
        print(f"  ✓ Matched '昨天' → {result}")
        return result
    if "今天" in message:
        print(f"  ✓ Matched '今天' → {today}")
        return today

    # ISO format: YYYY-MM-DD, YYYY/MM/DD, YYYY年MM月DD日
    iso_match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", message)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        result = date(year, month, day)
        print(f"  ✓ Matched ISO format: year={year}, month={month}, day={day} → {result}")
        return result

    # Chinese format: MM月DD日
    zh_match = re.search(r"(\d{1,2})月(\d{1,2})日", message)
    if zh_match:
        month, day = map(int, zh_match.groups())
        target = date(today.year, month, day)
        if target < today - timedelta(days=180):
            target = date(today.year + 1, month, day)
        print(f"  ✓ Matched Chinese format: month={month}, day={day} → {target}")
        return target

    # Dot format: MM.DD日
    dot_match = re.search(r"(\d{1,2})\.(\d{1,2})日?", message)
    if dot_match:
        month, day = map(int, dot_match.groups())
        target = date(today.year, month, day)
        if target < today - timedelta(days=180):
            target = date(today.year + 1, month, day)
        print(f"  ✓ Matched dot format: month={month}, day={day} → {target}")
        return target

    # No match, return today
    print(f"  ✗ No format matched, returning today → {today}")
    return today


# Test cases
test_cases = [
    ("6.11日在杭州", date(2026, 6, 11), "User's reported input"),
    ("6月11日在杭州", date(2026, 6, 11), "Chinese format with 月 and 日"),
    ("6-11日在杭州", None, "Dash format (may not match)"),
    ("明天在杭州", date(2026, 6, 11), "Tomorrow"),
    ("昨天在杭州", date(2026, 6, 9), "Yesterday"),
    ("2026-06-11在杭州", date(2026, 6, 11), "ISO format"),
    ("2026年6月11日在杭州", date(2026, 6, 11), "Full Chinese date"),
]

print("=" * 80)
print("Date Parsing Test Results")
print("=" * 80)

for message, expected, description in test_cases:
    print(f"\nTest: {description}")
    result = _target_date_from_message(message, TODAY)
    status = "✅" if expected is None or result == expected else "❌"
    print(f"  Result: {result}")
    if expected:
        print(f"  Expected: {expected}")
    print(f"  Status: {status}")
    print("-" * 40)

print("\n" + "=" * 80)
print("Summary: Check which formats are not matching correctly")
print("=" * 80)
