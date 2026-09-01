FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# HF Spaces runs the container as UID 1000. Create matching user and give it
# a writable home + workdir so SQLite and logs work without root.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

COPY --chown=user pyproject.toml README.md ./
COPY --chown=user src ./src
RUN pip install --no-cache-dir --user .

# HF Spaces default port is 7860; local Docker uses 8080 unless PORT set.
ENV DB_PATH=/home/user/app/data/reviewer.db PUBLIC_MODE=1
EXPOSE 7860
CMD sh -c "uvicorn reviewer.web.app:app --host 0.0.0.0 --port ${PORT:-7860}"
