FROM python:3.12-slim

# Install curl to download kubectl
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Download and install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Set up the Python working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application script
COPY ffmpeg_assistant.py .

# We do NOT copy the .env file here for security reasons. 
# We will inject the API key using a Kubernetes Secret later.

CMD ["python", "ffmpeg_assistant.py"]