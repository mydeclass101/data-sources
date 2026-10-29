FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi==0.141.1 uvicorn==0.54.0
WORKDIR /app
COPY app.py .
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
