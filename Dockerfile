FROM node:22-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/ecommerce.db FRONTEND_DIST=/app/web PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/seed_db.py ./seed_db.py
COPY --from=frontend /web/dist ./web
COPY scripts/start.sh ./start.sh
RUN python seed_db.py --path /app/data/ecommerce.db \
    && chmod 444 /app/data/ecommerce.db \
    && chmod +x /app/start.sh \
    && useradd --create-home appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health')"
CMD ["/app/start.sh"]
