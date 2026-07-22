FROM python:3.12-slim

WORKDIR /app

# Deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# No ports to expose — this is a gateway (outbound) worker, not a web service.
CMD ["python", "bot.py"]
