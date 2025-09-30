FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app

# Copy only requirements first (cache this layer)
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (cached if requirements.txt unchanged)
RUN playwright install --with-deps

# Copy code after dependencies (fast rebuilds for code changes)
COPY . /app

EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
