# The harness itself: Python, pinned dependencies, and the docker CLI to drive task containers.
FROM docker:28.3.3-cli@sha256:0135662b510037ea581d99c2e5929c5e01185139c0b86986a418bd4da0b98a44 AS dockercli
FROM ghcr.io/astral-sh/uv:0.9.2@sha256:6dbd7c42a9088083fa79e41431a579196a189bcee3ae68ba904ac2bf77765867 AS uv
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
ENV UV_PROJECT_ENVIRONMENT=/venv UV_LINK_MODE=copy HF_HUB_ENABLE_HF_TRANSFER=0 PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
ENTRYPOINT ["uv", "run", "--frozen", "--no-sync"]
