from datetime import date

from app.common import (
    NoEncontrado,
    ValidationError,
    admin_existe,
    obtener_colaborador,
    parse_event_body,
    path_params,
    response,
    siguiente_id,
    validar_cedula,
    validar_monto,
)
from app.db import get_conn


def handler(event, context):
    data = parse_event_body(event)
    ruta = path_params(event)

    try:
        cedula = validar_cedula(str(ruta.get("cedula", "")).strip())
        cupo_nuevo = validar_monto(data.get("cupo_mensual"))
        actualizado_por = validar_cedula(
            str(data.get("actualizado_por", "")).strip(), "actualizado_por"
        )
    except ValidationError as e:
        return response(400, {"errores": e.errores})

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        if not admin_existe(actualizado_por, cursor):
            return response(403, {"error": "administrador no registrado"})

        fila = obtener_colaborador(cedula, cursor)
        cupo_actual, saldo = fila["cupo_mensual"], fila["saldo"]

        if cupo_nuevo == cupo_actual:
            return response(
                200,
                {
                    "cedula": cedula,
                    "cupo_mensual": float(cupo_actual),
                    "saldo": float(saldo),
                    "mensaje": "sin cambios",
                },
            )

        hoy = date.today()

        cursor.execute(
            """INSERT INTO APP_CUPO_HISTORIAL
               (ID, CEDULA, CUPO_ANTERIOR, CUPO_NUEVO, ACTUALIZADO_POR, FECHA)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                siguiente_id(cursor, "APP_CUPO_HISTORIAL"),
                cedula,
                cupo_actual,
                cupo_nuevo,
                actualizado_por,
                hoy,
            ),
        )

        cursor.execute(
            """UPDATE APP_COLABORADORES
               SET CUPO_MENSUAL = %s, FECHA_ACTUALIZACION = %s
               WHERE CEDULA = %s""",
            (cupo_nuevo, hoy, cedula),
        )

        conn.commit()

    except NoEncontrado as e:
        return response(404, {"error": e.mensaje})
    except Exception as exc:  # error de DB
        if conn is not None:
            conn.rollback()
        return response(500, {"error": str(exc)})
    finally:
        if conn is not None:
            conn.close()

    return response(
        200,
        {
            "cedula": cedula,
            "cupo_anterior": float(cupo_actual),
            "cupo_nuevo": float(cupo_nuevo),
            "actualizado_por": actualizado_por,
            "saldo": float(saldo),
        },
    )
