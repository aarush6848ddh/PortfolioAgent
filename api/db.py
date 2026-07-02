import os
from contextlib import contextmanager

from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

load_dotenv()

_pool = SimpleConnectionPool(minconn=1, maxconn=5, dsn=os.environ["DATABASE_URL"])


@contextmanager
def get_db():
    """Borrow a pooled connection: `with get_db() as conn:`"""
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)
