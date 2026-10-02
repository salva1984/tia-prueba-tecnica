from app.common import (
    ValidationError,
    admin_existe,
    mover_saldo,
    parse_event_body,
    response,
    siguiente_id,
    validar_cedula,
)
from app.db import get_conn


def importar_gasclub(cursor, sgr, actualizado_por):
    sgr_id, cedula, referencia, total, fecha = sgr
    saldo_nuevo = mover_saldo(cursor, cedula, -total)
    cursor.execute(
        """INSERT INTO APP_MOVIMIENTOS
           (ID, CEDULA, TIPO, ORIGEN, MONTO, SALDO_RESULTANTE,
            REFERENCIA, SGR_ID, RUC_PROVEEDOR, ESTADO,
            REGISTRADO_POR, FECHA)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            siguiente_id(cursor, "APP_MOVIMIENTOS"),
            cedula,
            "GASTO",
            "GASCLUB",
            total,
            saldo_nuevo,
            referencia,
            sgr_id,
            None,
            None,
            actualizado_por,
            fecha,
        ),
    )


def handler(event, context):
    """POST /sincronizaciones/gasclub — body: {actualizado_por}."""
    data = parse_event_body(event)

    try:
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

        cursor.execute("SELECT CEDULA FROM APP_COLABORADORES")
        registradas = set(fila[0] for fila in cursor.fetchall())

        importados = 0
        sin_cambios = 0
        ignorados = 0

        if registradas:
            cursor.execute(
                "SELECT ID, CEDULA, REFERENCIA, TOTAL, FECHA FROM SGR_GASCLUB_GASTOS"
            )
            for sgr in cursor.fetchall():
                sgr_id, cedula, referencia, total, fecha = sgr

                if cedula not in registradas:
                    ignorados += 1
                    continue

                cursor.execute(
                    """SELECT ID FROM APP_MOVIMIENTOS
                       WHERE SGR_ID = %s AND ORIGEN = %s""",
                    (sgr_id, "GASCLUB"),
                )
                if cursor.fetchone() is None:
                    importar_gasclub(cursor, sgr, actualizado_por)
                    importados += 1
                else:
                    sin_cambios += 1

        conn.commit()
    except Exception as exc:  # error de DB (incluida conexion): rollback y 500
        if conn is not None:
            conn.rollback()
        return response(500, {"error": str(exc)})
    finally:
        if conn is not None:
            conn.close()

    return response(
        200,
        {
            "importados": importados,
            "sin_cambios": sin_cambios,
            "ignorados": ignorados,
            "actualizado_por": actualizado_por,
        },
    )
