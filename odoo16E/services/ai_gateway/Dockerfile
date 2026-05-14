FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app/app

EXPOSE 8071
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8071"]
