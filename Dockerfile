# Use the official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code into the container
COPY main.py .

# Expose the port the app will run on. Railway provides the $PORT variable.
EXPOSE 8000

# The command to run your application using uvicorn.
# It listens on all network interfaces (0.0.0.0) and on the port specified by Railway.

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
