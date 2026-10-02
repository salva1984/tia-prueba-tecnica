from datetime import date
from decimal import Decimal

from app.common import (
    ValidationError,
    colaborador_existe,
    parse_event_body,
    response,
    siguiente_id,
    validar_cedula,
    validar_monto,
)
from app.db import get_conn


def handler(event, context):
    """POST /colaboradores — body: {cedula, cupo_mensual}."""
    data = parse_event_body(event)

    try:
        cedula = validar_cedula(str(data.get("cedula", "")).strip())
        cupo = validar_monto(data.get("cupo_mensual"))
    except ValidationError as e:
        return response(400, {"errores": e.errores})

    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        if colaborador_existe(cedula, cur):
            return response(409, {"error": "el colaborador ya existe"})

        nuevo_id = siguiente_id(cur, "APP_COLABORADORES")

        hoy = date.today()
        cur.execute(
            """INSERT INTO APP_COLABORADORES
               (ID, CEDULA, CUPO_MENSUAL, SALDO, FECHA_CREACION, FECHA_ACTUALIZACION)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (nuevo_id, cedula, cupo, Decimal("0"), hoy, hoy),
        )
        conn.commit()
    except Exception as exc:  #
        if conn is not None:
            conn.rollback()
        return response(500, {"error": str(exc)})
    finally:
        if conn is not None:
            conn.close()

    return response(
        201,
        {
            "id": nuevo_id,
            "cedula": cedula,
            "cupo_mensual": float(cupo),
            "saldo": 0.0,
        },
    )
