# Stage 1: Build the Angular frontend
FROM node:22-slim AS build-frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build -- --configuration production

# Stage 2: Build the FastAPI backend
FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application
COPY app/ ./app/

# Copy the built Angular static files from Stage 1 into the FastAPI static directory
RUN mkdir -p /app/app/static
COPY --from=build-frontend /app/dist/frontend/browser/ /app/app/static/

# Create a workspace directory with appropriate permissions
RUN mkdir -p /app/workspace && chmod 755 /app/workspace

# Expose the FastAPI port
EXPOSE 8000

# Run the uvicorn server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
