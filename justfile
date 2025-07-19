lint:
  uv run ruff check --fix && uv run ruff format

type:
  uv run pyrefly check src