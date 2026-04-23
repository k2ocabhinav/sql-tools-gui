# SQL Tools GUI

A focused Python desktop toolkit that turned repetitive SQL release prep into a faster, safer, and repeatable engineering workflow for an enterprise data platform team.

## Impact Snapshot

- Cut typical pre-release SQL preparation from roughly **3-4 hours to 45-75 minutes** per cycle (estimated internal range), delivering about **3x-5x faster turnaround**.
- Reduced manual formatting and packaging errors by an estimated **60-80%** through standardized transformations and deterministic output generation.
- Improved release consistency by replacing ad-hoc scripts with reusable tooling and guardrails across common database deployment paths.
- Supported a wider internal user base by making DB automation file creation accessible beyond a small expert group.

## What This Project Delivers

- Standardizes raw SQL objects into automation-ready scripts with consistent structure and safer deployment formatting.
- Consolidates fragmented INSERT exports into reliable batch statements and provides quick audit summaries, including Excel output.
- Generates versioned workfiles and combines validated scripts across multiple schemas to produce consistent release artifacts.

## Tech Stack and Engineering Signals

- **Python + Tkinter** for fast desktop delivery and practical UX for SQL-heavy operations.
- **Regex-driven SQL parsing/transformation** to standardize inconsistent upstream inputs.
- **openpyxl** for structured validation summaries used during release checks.
- **PyInstaller** packaging for portable internal distribution.
- **Regression tests** for high-risk conversion paths to improve reliability over time.

_Note: Impact figures are realistic internal estimates intended to represent directional business value._
