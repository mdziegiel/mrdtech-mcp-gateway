FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir mcp
COPY server.py /app/server.py
RUN chmod 755 /app/server.py
USER 65532:65532
ENTRYPOINT ["/app/server.py"]
