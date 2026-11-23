FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt gunicorn
COPY backend backend
COPY frontend frontend
COPY data data
RUN useradd -m app && chown -R app /srv
USER app
WORKDIR /srv/backend
EXPOSE 8000
CMD ["sh", "-c", "gunicorn -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT} --timeout 120 app:app"]
