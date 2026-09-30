# Changelog

All notable changes to SQL Tools are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.0] - 2026-09-30

A ground-up rebuild of the desktop app on Qt, with the SQL and comparison logic
kept in separate, tested modules.

### Added
- Native Qt Widgets interface (PySide6) with a navigation rail, shared progress,
  an Activity drawer for summaries and diagnostics, and a **Reduce motion** option.
- One consistent Paste / Files / Folder source selector across INSERT Consolidator,
  DB Automation Converter and Multi-Schema Combiner, with your input kept when you
  switch modes or resize.
- Staged output: files are prepared in a staging folder, collisions are listed
  together, and nothing is replaced until you confirm. Cancelling or failing leaves
  existing files untouched.
- Cancellable background jobs, one at a time, so the window never freezes on large
  exports.
- Table Compare: multi-source comparison from CSV or SQL exports, key and column
  selection, search and status filters, selected-row details, and Excel export.
- New app icon and a refined visual theme.
- Local defaults for schemas, developer name and temporary prefix through an ignored
  `.sqltools-private.json`; builds made with `--public` always use generic defaults.
- One-command builds for macOS (`.app` and `.dmg`) and Windows x64 (portable ZIP and
  optional installer), with optional signing and notarization.
- Continuous integration on Windows x64, Apple Silicon and Intel macOS.

### Changed
- The macOS app is about 57 MB (15 MB as a `.dmg`): unused Qt parts and Python
  modules are left out, and the packaged app's smoke test runs each tool's real
  workflow to prove nothing needed was removed.
- Field validation clears when the problem is fixed, and keyboard focus and
  disabled states are clearly visible.

### Fixed
- The selected source mode and the visible input could disagree when changed through
  accessibility tools.
- Stale validation messages could survive **Clear**.
- Table Compare could enable **Remove** with nothing selected, and could leave a
  previous row's details or filters showing after the data changed.
- A long error message could force the window to an enormous minimum width.
- Pages with two columns could scroll sideways when text rendered wider than expected
  (for example on Windows or with a larger text size). Columns now stack whenever they
  would not fit side by side.
- The macOS disk image opened to a bare `Contents` folder instead of the app. It now
  contains `SQL Tools.app` and an Applications shortcut for drag-to-install.
