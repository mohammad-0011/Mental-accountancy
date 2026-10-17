# سرور لایسنس صبا روی میزبان کانتینری (justrunmy.app، VPS، ...)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# تک‌کارگر: نخِ نظرسنجی بات فقط در یک نمونه اجرا می‌شود (قفل پایگاه‌داده هم
# نگهبان دوم است). چند ریسمان برای پاسخ‌گویی هم‌زمان به برنامهٔ مشتریان.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120 app:app"]
