FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH="/app:/app/backend:/app/backend/generated"

COPY requirements/detector.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

CMD ["python", "backend/detector.py"]
