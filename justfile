lint:
  uv run ruff check --fix && uv run ruff format

lint-check:
  uv run ruff check && uv run ruff format --check

type:
  uv run pyrefly check src

test:
  uv run python -m pytest tests

bench:
  uv run --group bench python -m richbench tests/benchmarks