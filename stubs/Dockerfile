FROM ghcr.io/astral-sh/uv:0.13.8 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
RUN useradd --create-home --uid 10001 app
COPY --chown=app:app stubs ./stubs
USER app
EXPOSE 8010
CMD [".venv/bin/python", "-m", "stubs.bootstrap"]
