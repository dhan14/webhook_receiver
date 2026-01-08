# Dockerfile

# Gunakan base image Python yang ringan
FROM python:3.12-slim

# Tetapkan direktori kerja
WORKDIR /app

# Non-buffering output, memastikan log real-time
ENV PYTHONUNBUFFERED 1

# Salin requirements.txt dan instal dependensi
# CATATAN: Pastikan requirements.txt TIDAK berisi gunicorn jika Anda tidak ingin menginstalnya
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin sisa kode aplikasi
COPY . .

# Mengatur port yang diekspos
EXPOSE 3031

# Command default untuk menjalankan aplikasi dengan UVICORN TUNGGAL dan RELOAD
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3031", "--reload"]
