"""
Portfolio suitability checker.

Defines client risk profiles with target asset allocations and assesses whether
a portfolio is suitable for a profile, i.e. whether each asset class sits
within its tolerance band around the target weight.

Usage:
    python portfolio_suitability.py                      # demo on sample portfolios
    python portfolio_suitability.py portfolios.csv       # assess portfolios from a CSV
    python portfolio_suitability.py portfolios.csv --trades

CSV columns: client, profile, equities, bonds, cash, alternatives
(holdings in any consistent currency units).

Exit code is 1 if any portfolio in the CSV is not suitable, otherwise 0.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ASSET_CLASSES = ("equities", "bonds", "cash", "alternatives")


class Status(Enum):
    WITHIN = "within tolerance"
    OVERWEIGHT = "overweight"
    UNDERWEIGHT = "underweight"


@dataclass(frozen=True)
class RiskProfile:
    name: str
    description: str
    target: dict[str, float]  # asset class -> target weight (%), sums to 100
    tolerance: float          # allowed drift in percentage points, either side

    def __post_init__(self) -> None:
        if set(self.target) != set(ASSET_CLASSES):
            raise ValueError(f"{self.name}: target must cover exactly {ASSET_CLASSES}")
        total = sum(self.target.values())
        if abs(total - 100) > 1e-9:
            raise ValueError(f"{self.name}: targets sum to {total}, expected 100")
        if self.tolerance <= 0:
            raise ValueError(f"{self.name}: tolerance must be positive")


PROFILES: dict[str, RiskProfile] = {
    p.name: p
    for p in (
        RiskProfile(
            "cautious",
            "Capital preservation first; low volatility, modest growth.",
            {"equities": 20, "bonds": 50, "cash": 25, "alternatives": 5},
            tolerance=5,
        ),
        RiskProfile(
            "balanced",
            "Blend of growth and stability; moderate volatility.",
            {"equities": 50, "bonds": 30, "cash": 10, "alternatives": 10},
            tolerance=5,
        ),
        RiskProfile(
            "growth",
            "Long-term capital growth; accepts significant volatility.",
            {"equities": 70, "bonds": 15, "cash": 5, "alternatives": 10},
            tolerance=7.5,
        ),
        RiskProfile(
            "adventurous",
            "Maximum long-term growth; high tolerance for loss.",
            {"equities": 85, "bonds": 5, "cash": 2, "alternatives": 8},
            tolerance=7.5,
        ),
    )
}


@dataclass
class Flag:
    asset_class: str
    actual: float
    target: float
    drift: float  # actual - target, percentage points
    status: Status


@dataclass
class SuitabilityResult:
    profile: RiskProfile
    weights: dict[str, float]
    flags: list[Flag] = field(default_factory=list)

    @property
    def suitable(self) -> bool:
        return all(f.status is Status.WITHIN for f in self.flags)

    @property
    def breaches(self) -> list[Flag]:
        return [f for f in self.flags if f.status is not Status.WITHIN]


def to_weights(holdings: dict[str, float]) -> dict[str, float]:
    """Convert holdings (any currency units) into percentage weights."""
    unknown = set(holdings) - set(ASSET_CLASSES)
    if unknown:
        raise ValueError(f"Unknown asset classes: {sorted(unknown)}")
    if any(v < 0 for v in holdings.values()):
        raise ValueError("Holdings must be non-negative")
    total = sum(holdings.values())
    if total <= 0:
        raise ValueError("Portfolio has no value")
    return {ac: 100 * holdings.get(ac, 0.0) / total for ac in ASSET_CLASSES}


def assess_suitability(holdings: dict[str, float], profile_name: str) -> SuitabilityResult:
    """Check a portfolio against a risk profile and flag drift outside tolerance."""
    try:
        profile = PROFILES[profile_name.lower()]
    except KeyError:
        raise ValueError(f"Unknown profile '{profile_name}'. Options: {sorted(PROFILES)}")

    weights = to_weights(holdings)
    result = SuitabilityResult(profile=profile, weights=weights)

    for ac in ASSET_CLASSES:
        drift = weights[ac] - profile.target[ac]
        if drift > profile.tolerance:
            status = Status.OVERWEIGHT
        elif drift < -profile.tolerance:
            status = Status.UNDERWEIGHT
        else:
            status = Status.WITHIN
        result.flags.append(Flag(ac, weights[ac], profile.target[ac], drift, status))
    return result


def rebalancing_trades(holdings: dict[str, float], profile_name: str) -> dict[str, float]:
    """Cash amounts to buy (+) or sell (-) per asset class to return to target."""
    profile = PROFILES[profile_name.lower()]
    total = sum(holdings.values())
    return {
        ac: round(total * profile.target[ac] / 100 - holdings.get(ac, 0.0), 2)
        for ac in ASSET_CLASSES
    }


def report(result: SuitabilityResult) -> str:
    p = result.profile
    lines = [
        f"Profile: {p.name} (tolerance ±{p.tolerance}pp) - {p.description}",
        f"{'Asset class':<14}{'Actual %':>9}{'Target %':>10}{'Drift pp':>10}  Status",
    ]
    for f in result.flags:
        marker = "" if f.status is Status.WITHIN else "  <-- FLAG"
        lines.append(
            f"{f.asset_class:<14}{f.actual:>9.1f}{f.target:>10.1f}{f.drift:>+10.1f}  "
            f"{f.status.value}{marker}"
        )
    lines.append(
        "Result: SUITABLE" if result.suitable
        else f"Result: NOT SUITABLE ({len(result.breaches)} breach(es))"
    )
    return "\n".join(lines)


def _self_test() -> None:
    on_target = {"equities": 50, "bonds": 30, "cash": 10, "alternatives": 10}
    assert assess_suitability(on_target, "balanced").suitable

    edge = {"equities": 55, "bonds": 25, "cash": 10, "alternatives": 10}  # exactly 5pp
    assert assess_suitability(edge, "balanced").suitable

    drifted = {"equities": 70, "bonds": 15, "cash": 5, "alternatives": 10}
    res = assess_suitability(drifted, "balanced")
    assert not res.suitable
    assert {f.asset_class for f in res.breaches} == {"equities", "bonds"}

    trades = rebalancing_trades(drifted, "balanced")
    assert abs(sum(trades.values())) < 0.05  # trades net to zero

    for p in PROFILES.values():  # all targets valid
        assert abs(sum(p.target.values()) - 100) < 1e-9


def load_portfolios_from_csv(path: str | Path) -> list[tuple[str, str, dict[str, float]]]:
    """Read (client, profile, holdings) rows from a CSV file.

    Required columns (case-insensitive): client, profile, equities, bonds,
    cash, alternatives. Blank asset cells are treated as zero.
    """
    required = {"client", "profile", *ASSET_CLASSES}
    rows: list[tuple[str, str, dict[str, float]]] = []

    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = {(name or "").strip().lower() for name in (reader.fieldnames or [])}
        missing = required - header
        if missing:
            raise ValueError(f"CSV is missing column(s): {sorted(missing)}")

        for line_no, raw in enumerate(reader, start=2):  # line 1 is the header
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            try:
                holdings = {ac: float(row[ac] or 0) for ac in ASSET_CLASSES}
            except ValueError:
                raise ValueError(f"Line {line_no}: non-numeric holding for '{row['client']}'")
            rows.append((row["client"], row["profile"], holdings))

    return rows


DEMO_PORTFOLIOS = [
    ("Demo A", "balanced", {"equities": 62_000, "bonds": 18_000, "cash": 8_000, "alternatives": 12_000}),
    ("Demo B", "cautious", {"equities": 21_000, "bonds": 49_000, "cash": 24_000, "alternatives": 6_000}),
    ("Demo C", "growth", {"equities": 45_000, "bonds": 30_000, "cash": 15_000, "alternatives": 10_000}),
]


def run(portfolios, show_trades: bool = True) -> int:
    """Print a suitability report per portfolio. Returns the number not suitable."""
    unsuitable = 0
    for client, profile_name, holdings in portfolios:
        try:
            result = assess_suitability(holdings, profile_name)
        except ValueError as exc:
            print(f"Client: {client}\n  Error: {exc}\n")
            unsuitable += 1
            continue
        print(f"Client: {client}")
        print(report(result))
        if show_trades and not result.suitable:
            trades = rebalancing_trades(holdings, profile_name)
            print("Suggested trades:", {k: f"{v:+,.0f}" for k, v in trades.items()})
        if not result.suitable:
            unsuitable += 1
        print()
    print(f"Summary: {len(portfolios) - unsuitable} of {len(portfolios)} suitable")
    return unsuitable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess portfolio suitability against client risk profiles.")
    parser.add_argument("csv_file", nargs="?", help="CSV of portfolios; omit to run the demo")
    parser.add_argument("--trades", action="store_true",
                        help="show suggested rebalancing trades (always shown in the demo)")
    args = parser.parse_args(argv)

    if args.csv_file is None:
        _self_test()
        run(DEMO_PORTFOLIOS, show_trades=True)
        return 0

    try:
        portfolios = load_portfolios_from_csv(args.csv_file)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2
    return 1 if run(portfolios, show_trades=args.trades) else 0


if __name__ == "__main__":
    raise SystemExit(main())
