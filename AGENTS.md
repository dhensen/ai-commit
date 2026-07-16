# Repository Guidelines

## Project Structure & Module Organization

The application uses a small `src` layout. `src/ai_commit/commit.py` contains the CLI, Git subprocess integration, OpenAI request logic, and `.ai-commit.yml` handling; `src/ai_commit/__init__.py` marks the package. Tests live in `tests/test_commit.py`. Packaging metadata and console entry points live in `pyproject.toml`, while `uv.lock` pins dependencies. `install.sh` installs the local package as a `uv` tool. There are no assets or CI workflows.

## Build, Test, and Development Commands

- `uv sync` creates or refreshes the Python 3.11+ development environment from `uv.lock`.
- `uv run --frozen python -m unittest discover -s tests -v` runs the test suite without changing `uv.lock`.
- `uv build` produces source and wheel distributions in `dist/`.
- `./install.sh` reinstalls the CLI globally as a `uv`-managed tool.
- `OPENAI_API_KEY=... uv run ai-commit --dry-run` generates a message from staged changes without committing.
- `uv run ai-commit init` creates a repository-level `.ai-commit.yml` configuration without calling OpenAI.

Stage representative changes before exercising message generation. Test `--rewrite-head` only on a disposable branch because it amends the latest commit.

## Coding Style & Naming Conventions

Follow PEP 8 with four-space indentation. Use `snake_case` for functions and variables, `UPPER_CASE` for module constants, and short docstrings for non-obvious behavior. Keep subprocess commands as explicit argument lists and parse YAML with `yaml.safe_load`. No formatter or linter is currently configured; keep edits consistent with surrounding code. Commit `uv.lock` whenever dependencies change.

## Testing Guidelines

Tests use the standard-library `unittest` framework; no coverage threshold is configured. Name files `test_<module>.py` and methods `test_<behavior>`. Run the full suite plus `uv build` before submitting changes. Mock OpenAI calls and Git subprocesses so tests neither use the network nor create commits.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit subjects such as `feat: add ...`, `fix: handle ...`, and `chore: update ...`. Keep the summary imperative, focused, and under 72 characters. Pull requests should explain user-visible behavior, list validation commands, link relevant issues, and call out CLI, configuration, or environment-variable changes. Include terminal output for CLI changes when it helps reviewers.

## Security & Configuration

Never commit API keys or include them in logs. `.env` is ignored; `OPENAI_API_KEY` is required for generation and `init --distill`, while `GPT_MODEL` and `AI_COMMIT_ENV_FILE` are optional. Keep `.ai-commit.yml` limited to prompt instructions. Remember that generating a message sends the staged diff to the configured OpenAI model.
