# Frontend (Streamlit Chat UI) Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install merged deps (streamlit + ai_engine libs)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy UI code
COPY . .

EXPOSE 8501

# ai_engine code is mounted at /app/ai_engine via docker-compose volume
# PYTHONPATH lets `from agent import ...` and `import rag_engine` resolve
ENV PYTHONPATH="/app/ai_engine"

CMD ["streamlit", "run", "chat_ui.py", "--server.port=8501", "--server.address=0.0.0.0"]
