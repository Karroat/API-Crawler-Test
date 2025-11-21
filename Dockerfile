# Use the official Playwright Python image. We are updating the tag to a known,
# later stable version (v1.58.0-jammy) because v1.56.0-jammy was not found.
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- Explicitly install Playwright browsers for robust execution ---
# This ensures that the correct browser executables (like chromium) are downloaded
# inside your container, matching the installed Python package version.
RUN playwright install chromium --with-deps

# Copy your application code into the container
COPY main.py .

# Expose the port the app will run on. (Set to 8000, as defined in CMD)
EXPOSE 8000

# The command to run your application using uvicorn.
# It listens on all network interfaces (0.0.0.0) and on port 8000.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


