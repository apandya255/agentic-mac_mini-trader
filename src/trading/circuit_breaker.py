"""
Circuit breaker module for the autonomous trading loop.

Manages session-open NAV tracking and intraday drawdown threshold detection.
When the portfolio drawdown exceeds -2% from session open, the circuit breaker
activates and blocks new trade entries.

Requirements: 2.1, 2.2, 2.4, 5.1, 5.2, 5.3
"""

from dataclasses import dataclass
from pathlib import Path
import json

DRAWDOWN_THRESHOLD = -0.02  # -2%
DELEVERAGE_THRESHOLD = -0.03  # -3% triggers deleverage recommendation
EMERGENCY_THRESHOLD = -0.04  # -4% triggers emergency close-all recommendation

# Sidecar state file for persisting session_open_nav across failures
_SESSION_NAV_SIDECAR = Path(__file__).parent.parent.parent / "memos" / "state" / "session_nav.json"


@dataclass
class CircuitBreakerState:
    """State snapshot of the circuit breaker."""

    active: bool
    session_open_nav: float
    current_drawdown: float


def compute_intraday_drawdown(current_nav: float, session_open_nav: float) -> float:
    """
    Compute intraday drawdown as a fraction (negative means loss).

    Args:
        current_nav: Current portfolio NAV.
        session_open_nav: NAV recorded at session open (9:30 AM ET).

    Returns:
        Drawdown fraction. E.g., -0.02 means a 2% loss from session open.
        Returns 0.0 if session_open_nav <= 0 (edge case guard).
    """
    if session_open_nav <= 0:
        return 0.0
    return (current_nav - session_open_nav) / session_open_nav


def is_circuit_breaker_active(current_nav: float, session_open_nav: float) -> CircuitBreakerState:
    """
    Check if circuit breaker should be active.

    The circuit breaker activates when intraday drawdown reaches or exceeds -2%.

    Args:
        current_nav: Current portfolio NAV.
        session_open_nav: NAV recorded at session open.

    Returns:
        CircuitBreakerState with active flag, session_open_nav, and current drawdown.
    """
    drawdown = compute_intraday_drawdown(current_nav, session_open_nav)
    return CircuitBreakerState(
        active=(drawdown <= DRAWDOWN_THRESHOLD),
        session_open_nav=session_open_nav,
        current_drawdown=drawdown,
    )


def compute_progressive_deleverage(
    current_nav: float, session_open_nav: float
) -> str | None:
    """
    Returns None, 'deleverage', or 'emergency' based on drawdown level.

    - drawdown <= -4%: "emergency"
    - drawdown <= -3%: "deleverage"
    - drawdown > -3%: None (or circuit breaker handles -2% separately)

    Note: The circuit breaker (-2%) is handled separately by
    is_circuit_breaker_active(). This function only handles the
    higher thresholds.
    """
    if session_open_nav <= 0:
        return None
    drawdown = (current_nav - session_open_nav) / session_open_nav
    if drawdown <= EMERGENCY_THRESHOLD:
        return "emergency"
    elif drawdown <= DELEVERAGE_THRESHOLD:
        return "deleverage"
    return None


def reset_session_nav(book_path: Path) -> float:
    """
    Record session-open NAV from the book at 9:30 AM ET.

    Enhanced: handles corrupt/missing book file by sending a Telegram alert
    and retaining the previous session_open_nav from the sidecar state file.

    Args:
        book_path: Path to book.json file.

    Returns:
        The session-open NAV value that was recorded, or the previous
        session_open_nav from the sidecar if the book is unavailable.

    Requirements: 5.1, 5.2, 5.3
    """
    try:
        book = json.loads(book_path.read_text())
        session_nav = book.get("nav", 0)
        book["session_open_nav"] = session_nav
        book_path.write_text(json.dumps(book, indent=2))

        # Persist to sidecar for resilience
        _save_session_nav_sidecar(session_nav)

        return session_nav

    except (FileNotFoundError, json.JSONDecodeError) as e:
        # Send critical Telegram alert
        try:
            from src.telegram_bot import send_message

            send_message(
                f"Session NAV reset failed: {type(e).__name__}: {e}. "
                f"Retaining previous session_open_nav.",
                severity="critical",
            )
        except Exception:
            pass

        # Retain previous session_open_nav from sidecar
        return _load_session_nav_sidecar()


def _save_session_nav_sidecar(nav: float) -> None:
    """Persist session_open_nav to a sidecar file for resilience."""
    _SESSION_NAV_SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    _SESSION_NAV_SIDECAR.write_text(json.dumps({"session_open_nav": nav}))


def _load_session_nav_sidecar() -> float:
    """Load previous session_open_nav from sidecar file. Returns 0 if unavailable."""
    try:
        data = json.loads(_SESSION_NAV_SIDECAR.read_text())
        return data.get("session_open_nav", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
