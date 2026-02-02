# Python ka base image
FROM python:3.10-slim

# System updates aur Tesseract OCR + OpenCV dependencies (libGL) install karna
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# App folder banana
WORKDIR /app

# Requirements copy karke install karna
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baaki saara code copy karna
COPY . .

# Port expose karna (Flask ke liye)
EXPOSE 5000

# App start karne ki command
# Yahan 'main' teri file ka naam hai aur 'app' Flask object ka
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]