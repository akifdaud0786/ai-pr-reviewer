FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY orchestrator_service/ ./orchestrator_service/

# No exposed HTTP port -- this runs as a Celery worker process
CMD ["celery", "-A", "shared.celery_app.celery_app", "worker", "--loglevel=INFO", "--concurrency=4"]
