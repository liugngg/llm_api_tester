# Repository Guidelines

## Project Structure & Module Organization

This repository contains a compact desktop application. `llm_tester.py` implements the Tkinter interface, YAML loading, and API checks. `config.yaml` is an example provider/model configuration; `liug.ico` is the Windows application icon. `README.md` documents features and packaging. There is currently no separate source package, assets directory, or test directory, so keep focused changes in the existing layout unless the project grows.

## Build, Test, and Development Commands

- `uv sync` installs the dependencies declared in `pyproject.toml` from `uv.lock`.
- `uv run python llm_tester.py` launches the desktop application (requires a graphical session).
- `uv run python -m compileall llm_tester.py` performs a quick syntax check.
- Use the PyInstaller or Nuitka commands in `README.md` to build a Windows executable; run packaging from the repository root so the icon and configuration are available.

No automated test suite or build script is currently configured. When changing API or configuration behavior, manually verify loading a YAML file and testing at least one successful and one failing endpoint where practical.

## Coding Style & Naming Conventions

Use Python 3.12+, four spaces for indentation, `snake_case` for functions and variables, and `PascalCase` for classes. Keep UI updates and user-facing messages consistent with the existing Tkinter patterns. Use `yaml.safe_load` for configuration parsing, and keep network calls bounded by the configured timeout. There is no formatter or linter configured; keep imports tidy and match the surrounding style.

## Testing Guidelines

There are no committed tests or coverage requirements. If adding tests, place them in `tests/` and use `test_*.py` names so they can be discovered by pytest. Prefer tests for configuration parsing and API-result handling that do not require live credentials or network access.

## Commit & Pull Request Guidelines

Recent history uses concise messages with prefixes such as `fix:` and `chore:`; follow that pattern (for example, `fix: handle empty model lists`). Pull requests should explain the user-visible change, note manual or automated checks performed, and include screenshots for visible UI changes. Never include real API keys in commits or screenshots.

## Security & Configuration

Treat `config.yaml` as an example only. Replace placeholder keys locally and do not commit credentials, private endpoints, or test responses containing secrets. Keep examples sanitized and use environment-specific configuration outside version control when testing real providers.
