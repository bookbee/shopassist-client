# Builds the shopassist-client (storefront) image.
#
# COPY lines are explicit (no `COPY . .`) so a local .venv/, .git/, .env,
# and logs/ never end up in an image layer even if .dockerignore ever
# falls out of sync.
#
# mock_gateway.py is intentionally not copied in - this container always
# talks to a real, containerized shopassist API (see docker-compose.yml /
# shopassist-devops), so the local stdlib mock has nothing to do.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py config.py config.yaml ./
COPY chatbot ./chatbot
COPY components ./components
COPY pages ./pages
COPY utils ./utils
COPY data ./data
COPY styles ./styles
COPY assets ./assets
COPY .streamlit ./.streamlit

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
