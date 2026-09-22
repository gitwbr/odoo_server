FROM python:3.11-slim

WORKDIR /app

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock

COPY app /app/app

EXPOSE 8071
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8071"]
