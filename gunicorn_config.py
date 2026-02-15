"""
Gunicorn Configuration
=======================
Production WSGI server settings.

Usage:
    gunicorn wsgi:app -c gunicorn_config.py
"""

import os
import multiprocessing

# Server socket
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5000")

# Worker processes
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 8)))
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = os.environ.get("ACCESS_LOG", "-")
errorlog = os.environ.get("ERROR_LOG", "-")
loglevel = os.environ.get("LOG_LEVEL", "info")

# Process naming
proc_name = "vedic-astrology"

# Server mechanics
preload_app = True
max_requests = 1000
max_requests_jitter = 50
graceful_timeout = 30
