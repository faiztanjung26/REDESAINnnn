#!/bin/bash

# Path ke project
cd /home/cmms_app

# Aktifkan virtualenv jika ada (hapus baris ini kalau install system-wide)
# source /home/cmms_app/venv/bin/activate

# Jalankan gunicorn
exec gunicorn "app:create_app()" --config gunicorn.conf.py
