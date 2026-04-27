FROM python:3.12-slim

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/backend:/app/backend/generated"

# Install dependencies
COPY requirements/coordinator.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# COPY full project from build context
COPY . .

# Ensure Python can import the backend package
ENV PYTHONPATH=/app

CMD ["python", "backend/coordinator.py"]
