# Scripts

Utility and automation scripts for AskMyDocs AI.

## Planned Scripts

| Script | Purpose | Stage |
|--------|---------|-------|
| `download_filings.py` | Download SEC filings from EDGAR by ticker/CIK | Stage 1 |
| `ingest.py` | Run the full ingestion pipeline (parse → chunk → embed → store) | Stage 1 |
| `query.py` | CLI tool to query the system (for development/debugging) | Stage 2 |
| `evaluate.py` | Run offline evaluation against golden dataset | Stage 8 |
| `eval_report.py` | Generate human-readable evaluation report | Stage 8 |
| `setup_financebench.py` | Download and prepare FinanceBench dataset subset | Stage 8 |

## Usage Pattern

Scripts are CLI tools for development and operations. They are not part of the application runtime.

```bash
# Example (once implemented):
python scripts/download_filings.py --tickers NVDA,MSFT,GOOG --years 2023,2024
python scripts/ingest.py --source datasets/raw/
python scripts/evaluate.py --dataset datasets/evaluation/financebench-150.json
```

## Rules

- Scripts import from `app/` — they use the same code paths as the application.
- Scripts are not tested in unit tests (they are thin wrappers around use cases).
- Scripts handle CLI argument parsing and display; business logic lives in `app/`.
