# Feature: operational-reliability, Property 6: Atomic Book Write Integrity
"""
Property-based tests for atomic book write integrity.

For any book data (valid JSON dict), after `atomic_write_book` completes:
- The file contains exactly the new data (valid JSON, parseable, equals input)
- No .tmp file remains

For simulated failures:
- If the write is interrupted (simulate by killing after .tmp write),
  the original file remains intact

Edge case property:
- If an existing file has valid data and atomic_write_book is called with new data,
  the file always contains EITHER the old data or the new data (never corrupted).

Validates: Requirements 6.2
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Import atomic_write_book from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from run_cycle import atomic_write_book


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate random position dicts
position_strategy = st.fixed_dictionaries({
    "ticker": st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=5),
    "direction": st.sampled_from(["long", "short"]),
    "size_pct_nav": st.floats(min_value=0.01, max_value=0.10, allow_nan=False, allow_infinity=False),
    "entry_price": st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
})

# Generate random book dicts matching the book.json structure
book_strategy = st.fixed_dictionaries({
    "nav": st.floats(min_value=1000.0, max_value=100_000_000.0, allow_nan=False, allow_infinity=False),
    "positions": st.lists(position_strategy, min_size=0, max_size=5),
    "cash_pct": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
})


# ---------------------------------------------------------------------------
# Property 6: Atomic Book Write Integrity — Successful Write
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=book_strategy)
def test_property_6_atomic_write_produces_exact_data(data: dict):
    """
    **Validates: Requirements 6.2**

    Property 6: Atomic Book Write Integrity — For any book data (valid JSON dict),
    after `atomic_write_book` completes, the file contains exactly the new data
    (valid JSON, parseable, equals input) and no .tmp file remains.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        book_path = Path(tmpdir) / "book.json"

        # Write using atomic_write_book
        atomic_write_book(book_path, data)

        # 1. File must exist
        assert book_path.exists(), "book.json does not exist after atomic_write_book"

        # 2. File content must be valid JSON
        content = book_path.read_text()
        parsed = json.loads(content)

        # 3. Parsed content must equal the input data
        assert parsed == data, f"File content does not match input data"

        # 4. No .tmp file should remain
        tmp_path = book_path.with_suffix('.tmp')
        assert not tmp_path.exists(), f".tmp file remains after successful write: {tmp_path}"


# ---------------------------------------------------------------------------
# Property 6: Atomic Book Write Integrity — Old or New, Never Corrupted
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(old_data=book_strategy, new_data=book_strategy)
def test_property_6_file_contains_old_or_new_data_never_corrupted(
    old_data: dict, new_data: dict
):
    """
    **Validates: Requirements 6.2**

    Property 6: Atomic Book Write Integrity — If an existing file has valid data
    and atomic_write_book is called with new data, the file always contains EITHER
    the old data or the new data (never corrupted).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        book_path = Path(tmpdir) / "book.json"

        # Write initial (old) data
        book_path.write_text(json.dumps(old_data, indent=2))

        # Write new data atomically
        atomic_write_book(book_path, new_data)

        # Read back the file
        content = book_path.read_text()
        parsed = json.loads(content)

        # File must contain EITHER old_data or new_data (never corrupted)
        assert parsed == new_data or parsed == old_data, (
            "File contains neither old data nor new data — possible corruption"
        )

        # After successful completion, it should specifically be new_data
        assert parsed == new_data, (
            "After successful atomic_write_book, file should contain new data"
        )


# ---------------------------------------------------------------------------
# Property 6: Atomic Book Write Integrity — Simulated Failure Preserves Old State
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(old_data=book_strategy, new_data=book_strategy)
def test_property_6_simulated_failure_preserves_original(
    old_data: dict, new_data: dict
):
    """
    **Validates: Requirements 6.2**

    Property 6: Atomic Book Write Integrity — If the write is interrupted
    (simulated by making os.replace raise an error after .tmp is written),
    the original file remains intact.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        book_path = Path(tmpdir) / "book.json"
        tmp_path = book_path.with_suffix('.tmp')

        # Write initial (old) data
        book_path.write_text(json.dumps(old_data, indent=2))

        # Simulate a failure during os.replace by patching it to raise OSError
        with patch("run_cycle.os.replace", side_effect=OSError("Simulated disk failure")):
            try:
                atomic_write_book(book_path, new_data)
            except OSError:
                pass  # Expected — simulated failure

        # The original file should still contain old_data (intact)
        content = book_path.read_text()
        parsed = json.loads(content)
        assert parsed == old_data, (
            "Original book.json was corrupted despite os.replace failure"
        )
