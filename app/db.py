import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_conn():

    faltantes = [
        k
        for k in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
        if not os.getenv(k)
    ]
    if faltantes:
        raise RuntimeError(f"faltan variables de entorno: {', '.join(faltantes)}")

    host = os.getenv("DB_HOST")
    try:
        port = int(os.getenv("DB_PORT"))
    except (TypeError, ValueError):
        raise RuntimeError(
            f"DB_PORT invalido: {os.getenv('DB_PORT')!r} (debe ser numero)"
        )

    try:
        return psycopg2.connect(
            host=host,
            port=port,
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
    except psycopg2.OperationalError as exc:
        raise RuntimeError(
            f"no se pudo conectar a Postgres en {host}:{port}/"
            f"{os.getenv('DB_NAME')} como {os.getenv('DB_USER')}: {exc}"
        ) from exc
