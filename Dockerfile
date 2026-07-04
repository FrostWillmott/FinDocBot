FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN groupadd -r findocbot && useradd -r -g findocbot -d /app findocbot

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-editable

COPY src /app/src
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"

USER findocbot

EXPOSE 8000

CMD ["uvicorn", "findocbot.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
