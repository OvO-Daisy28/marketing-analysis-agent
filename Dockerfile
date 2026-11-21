FROM node:24-bookworm-slim AS web
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.16
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY marketing/ marketing/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY skills/ skills/
COPY --from=web /app/web/dist/ web/dist/
RUN useradd --create-home --uid 10001 app && mkdir -p data artifacts && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "marketing.api:app", "--host", "0.0.0.0", "--port", "8000"]
