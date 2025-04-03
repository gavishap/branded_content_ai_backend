FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose the port
EXPOSE 5000

# Run the application with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"] 
