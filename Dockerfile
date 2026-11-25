FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data APP_HOST=0.0.0.0
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk libreoffice-writer && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY safety_report ./safety_report
COPY web ./web
COPY reference ./reference
COPY skills ./skills
COPY docs/TESTING.md ./docs/TESTING.md
COPY third_party ./third_party
RUN useradd --uid 10001 --create-home appuser && mkdir /app/data && chown appuser:appuser /app/data
USER appuser
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/').read(1)"
CMD ["python", "-m", "safety_report"]
