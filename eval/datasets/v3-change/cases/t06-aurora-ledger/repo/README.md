# Aurora ledger

The ledger helper totals open entries.
Amounts are signed: credits reduce the open total.
Settled entries are excluded.

## Local checks

Install pytest in a virtual environment.
Run `python -m pytest -v` from the repository root.
The test suite covers credits and an empty ledger.

## Data shape

Each entry has an integer amount.
Each entry has a boolean settled flag.
The helper returns an integer.
