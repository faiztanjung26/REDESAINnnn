import multiprocessing

# Server socket
bind = "0.0.0.0:5002"

# Workers — gevent untuk async I/O (cocok untuk Flask + banyak user)
worker_class = "gevent"
workers = multiprocessing.cpu_count() * 2 + 1  # Otomatis sesuai CPU server
worker_connections = 100  # Max concurrent connections per worker

# Timeout
timeout = 120
keepalive = 5

# Logging
accesslog = "-"   # stdout
errorlog = "-"    # stdout
loglevel = "info"

# Restart workers setelah N request (prevent memory leak)
max_requests = 1000
max_requests_jitter = 100
