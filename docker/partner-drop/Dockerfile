# The marketplace partner: drops yesterday's orders as a CSV into ./inbox/marketplace every night.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Bangkok
WORKDIR /app
RUN pip install --no-cache-dir "psycopg[binary]==3.3.5"
COPY drop.py .
CMD ["python", "drop.py"]
