FROM python:3.12-alpine

WORKDIR /app
RUN pip install --no-cache-dir mcp
COPY app/server.py /app/server.py
RUN chmod 755 /app/server.py

ENTRYPOINT ["/app/server.py"]
