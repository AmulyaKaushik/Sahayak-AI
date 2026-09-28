from contextlib import contextmanager

import psycopg

from settings import settings


@contextmanager
def get_connection():
    with psycopg.connect(settings.database_url) as conn:
        yield conn
