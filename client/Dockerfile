FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

ENTRYPOINT ["python", "client_encrypt_upload.py"]
CMD ["encrypt"]
