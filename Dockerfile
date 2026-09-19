FROM python:3.12-slim

WORKDIR /app

# Deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py settings_store.py .

# Per-server settings persist to AVATAR_SHIELD_DB (default /data/avatar-shield.db).
# Mount a persistent volume at /data or settings are lost on every redeploy.
# No VOLUME instruction: Railway rejects Dockerfiles that declare one; attach
# a platform volume at /data instead (docker run -v works the same locally).

# No ports to expose — this is a gateway (outbound) worker, not a web service.
CMD ["python", "bot.py"]
