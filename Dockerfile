FROM python:3.11-alpine

WORKDIR /app

# Install only what’s needed for runtime
RUN apk add --no-cache libffi openssl curl

COPY ./api/main.py requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
