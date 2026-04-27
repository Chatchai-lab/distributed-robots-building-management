FROM python:3.12-slim

WORKDIR /app

COPY requirements/servicebot.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

CMD ["python3", "-m", "backend.ServiceBot", "--role", "cleaner"]
