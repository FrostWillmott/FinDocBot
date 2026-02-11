FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md LICENSE ruff.toml /app/
COPY src /app/src

RUN uv pip install --system .

EXPOSE 8000

CMD ["uvicorn", "findocbot.main:app", "--host", "0.0.0.0", "--port", "8000"]
