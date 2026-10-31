# See https://docs.astral.sh/uv/guides/integration/docker/

FROM ghcr.io/astral-sh/uv:bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_CACHE=1

RUN --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

ADD . /app

RUN uv sync --frozen --no-dev

RUN chown -R nobody:nogroup /app

ENV PATH="/app/.venv/bin:$PATH"

USER nobody

EXPOSE 8000

CMD ["uvicorn", "pokecoach_python.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
