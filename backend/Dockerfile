FROM python:3.14-slim

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Run as an unprivileged user; nothing here needs root at runtime.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# # To build the Docker image, run:
# # docker build -t my-fastapi-app .
