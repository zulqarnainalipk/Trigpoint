FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV SITE_CURATOR_HOST=0.0.0.0
EXPOSE 8765
# The tool has no sign-in. Publish the port to this computer only:
#   docker run -p 127.0.0.1:8765:8765 trigpoint
CMD ["python", "server.py"]
