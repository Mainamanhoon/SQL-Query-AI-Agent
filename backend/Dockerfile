FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_PATH=/app/data/ecommerce.db CHAT_DATABASE_URL=sqlite:////app/chat-data/chat_sessions.db
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/seed_db.py ./seed_db.py
RUN python seed_db.py --path /app/data/ecommerce.db \
    && chmod 444 /app/data/ecommerce.db \
    && useradd --create-home appuser \
    && mkdir -p /app/chat-data \
    && chown appuser:appuser /app/chat-data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
