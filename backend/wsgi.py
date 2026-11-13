"""Production entrypoint: gunicorn wsgi:app --bind 0.0.0.0:8000"""

from app import create_app

app = create_app()
