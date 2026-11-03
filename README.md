# Portfolio Suitability Tool

A lightweight Python tool for **assessing portfolio suitability**. It maps clients to risk profiles (cautious, balanced, growth, adventurous), checks whether a portfolio's asset allocation matches the profile, and flags any asset class that has drifted outside its tolerance band. When a portfolio is out of line, it calculates the trades needed to bring it back to target.

Built with the standard library only: no dependencies, nothing to install.

> **Illustrative only.** Target allocations and tolerances are example values chosen to demonstrate the logic. They are not investment advice and are not taken from any firm's model portfolios.

---

## Why this exists

In wealth management, a core recurring task is checking that what a client actually holds still matches what was agreed for their risk profile. Markets move, allocations drift, and portfolios that were suitable at the start of the year may not be by the end of it.

This project automates that check in a transparent, testable way:

1. Define what "suitable" means for each risk profile.
2. Compare a client's actual holdings against it.
3. Flag exactly which asset classes are out of tolerance, by how much, and in which direction.
4. Show what it would take to rebalance.

## Features

- **Four risk profiles** with target allocations across equities, bonds, cash and alternatives
- **Drift detection** with a per-profile tolerance band, flagging each asset class as overweight, underweight or within tolerance
- **Rebalancing suggestions** showing the buy/sell amount per asset class to return to target
- **Batch mode:** assess many clients at once from a CSV file
- **Script-friendly CLI** with meaningful exit codes, so it can run as part of a scheduled check
- **Input validation:** unknown profiles, negative holdings, malformed CSVs and bad numbers produce clear errors rather than silent wrong answers
- **23 unit tests** covering the logic, edge cases and CLI

## Quick start

You need Python 3.9 or newer.

```bash
git clone https://github.com/YOUR-USERNAME/portfolio-suitability-tool.git
cd portfolio-suitability-tool

python portfolio_suitability.py                    # demo on three sample portfolios
python portfolio_suitability.py portfolios.csv     # assess the sample CSV
python -m unittest -v                              # run the tests
```

(On some systems the command is `python3` or `py` rather than `python`.)

## Risk profiles

| Profile | Equities | Bonds | Cash | Alternatives | Tolerance |
|---|---|---|---|---|---|
| Cautious | 20% | 50% | 25% | 5% | ±5pp |
| Balanced | 50% | 30% | 10% | 10% | ±5pp |
| Growth | 70% | 15% | 5% | 10% | ±7.5pp |
| Adventurous | 85% | 5% | 2% | 8% | ±7.5pp |

*pp = percentage points.* More aggressive profiles get a wider tolerance band, reflecting that higher-equity portfolios naturally swing more with markets.

## How it works

**Suitability.** For each asset class the tool computes drift, the actual weight minus the target weight:

```
drift = actual weight % − target weight %
```

| Condition | Status |
|---|---|
| drift > +tolerance | Overweight (flagged) |
| drift < −tolerance | Underweight (flagged) |
| otherwise | Within tolerance |

A portfolio is **suitable** only if *every* asset class is within tolerance. Sitting exactly on the boundary counts as within tolerance.

**Rebalancing.** The suggested trade for each asset class is:

```
trade = total portfolio value × target weight − current holding
```

Positive means buy, negative means sell. Because trades are calculated against the portfolio's current total value, they net to zero: you sell what is overweight to fund what is underweight.

## Usage

### Command line

```bash
python portfolio_suitability.py                           # demo mode
python portfolio_suitability.py portfolios.csv            # assess a CSV
python portfolio_suitability.py portfolios.csv --trades   # also show suggested trades
```

**CSV format** (column names are case-insensitive; blank asset cells count as zero):

```csv
client,profile,equities,bonds,cash,alternatives
Client 001,balanced,50000,30000,10000,10000
Client 002,balanced,62000,18000,8000,12000
Client 003,cautious,21000,49000,24000,6000
```

Holdings can be in any consistent currency unit, since they are converted to percentage weights internally.

**Exit codes**

| Code | Meaning |
|---|---|
| `0` | All portfolios are suitable |
| `1` | At least one portfolio is not suitable (or names an unknown profile) |
| `2` | The CSV could not be read or is malformed |

**Example output**

```
Client: Client 002
Profile: balanced (tolerance ±5pp) - Blend of growth and stability; moderate volatility.
Asset class    Actual %  Target %  Drift pp  Status
equities           62.0      50.0     +12.0  overweight  <-- FLAG
bonds              18.0      30.0     -12.0  underweight  <-- FLAG
cash                8.0      10.0      -2.0  within tolerance
alternatives       12.0      10.0      +2.0  within tolerance
Result: NOT SUITABLE (2 breach(es))
Suggested trades: {'equities': '-12,000', 'bonds': '+12,000', 'cash': '+2,000', 'alternatives': '-2,000'}
```

### As a Python module

```python
from portfolio_suitability import assess_suitability, rebalancing_trades, report

holdings = {"equities": 62_000, "bonds": 18_000, "cash": 8_000, "alternatives": 12_000}

result = assess_suitability(holdings, "balanced")

print(result.suitable)                            # False
print([f.asset_class for f in result.breaches])   # ['equities', 'bonds']
print(report(result))                             # formatted table with flags
print(rebalancing_trades(holdings, "balanced"))   # buy/sell amounts per asset class
```

## Customising profiles

Profiles live in the `PROFILES` dictionary in `portfolio_suitability.py`. To add or change one:

```python
RiskProfile(
    "income",
    "Prioritises steady income with limited volatility.",
    {"equities": 30, "bonds": 55, "cash": 10, "alternatives": 5},
    tolerance=5,
)
```

Each `RiskProfile` validates itself on creation: targets must cover exactly the four asset classes, sum to 100, and the tolerance must be positive. A bad definition fails immediately instead of producing misleading results later.

## Project structure

```
portfolio-suitability-tool/
├── portfolio_suitability.py        # profiles, suitability check, rebalancing, CSV loader, CLI
├── test_portfolio_suitability.py   # unit tests
├── portfolios.csv                  # sample input
└── README.md
```

## Testing

```bash
python -m unittest -v
```

The suite covers:

- weight conversion and scale invariance
- profile validation (bad sums, missing asset classes, invalid tolerance)
- tolerance boundaries: exactly on the limit passes, just beyond it is flagged
- breach direction (overweight versus underweight)
- the same portfolio being suitable for one profile but not another
- rebalancing maths: trades net to zero, and applying them lands on target
- CSV loading, missing columns, non-numeric values (with line numbers) and CLI exit codes

## Limitations

This is a demonstration of the core logic, not a compliance system. In particular:

- It checks **asset-class allocation only**. A genuine suitability assessment also considers the client's objectives, time horizon, capacity for loss, liquidity needs, tax position and regulatory requirements.
- Rebalancing suggestions ignore transaction costs, tax and minimum trade sizes.
- Only four broad asset classes are modelled. There are no sub-asset-class, currency, sector or concentration checks.
- Profile targets and tolerances are illustrative and not calibrated to any real investment policy.

## Possible extensions

- Load profiles from a JSON or YAML config instead of editing code
- Add relative drift bands (for example ±20% of target) alongside absolute ones
- Concentration limits on single holdings or sectors
- Export results to CSV or Excel for review
- Track drift over time to show when a portfolio first fell out of tolerance

## Author

Built by Joseff Elis Baglin, a physics graduate (Queen Mary University of London) with an interest in wealth management operations.

## Disclaimer

This software is provided for educational and demonstration purposes only and does not constitute financial advice.
