FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8765

EXPOSE 8765

CMD ["python", "main.py"]
