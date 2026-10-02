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


def importar_factura(cursor, sgr, actualizado_por):
    sgr_id, cedula, numero, ruc, total, fecha, estado = sgr
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
            "FACTURA",
            total,
            saldo_nuevo,
            numero,
            sgr_id,
            ruc,
            estado,
            actualizado_por,
            fecha,
        ),
    )


def reflejar_estado(cursor, mov_id, estado):
    cursor.execute(
        "UPDATE APP_MOVIMIENTOS SET ESTADO = %s WHERE ID = %s",
        (estado, mov_id),
    )


def handler(event, context):
    """POST /sincronizaciones/facturas — body: {actualizado_por}."""
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
        actualizados = 0
        sin_cambios = 0
        ignorados = 0

        if registradas:
            cursor.execute(
                """SELECT ID, CEDULA, NUMERO_FACTURA, RUC_PROVEEDOR,
                          TOTAL, FECHA, ESTADO
                   FROM SGR_FACTURAS"""
            )
            for sgr in cursor.fetchall():
                sgr_id, cedula, numero, ruc, total, fecha, estado = sgr

                if cedula not in registradas:
                    ignorados += 1
                    continue

                cursor.execute(
                    """SELECT ID, ESTADO FROM APP_MOVIMIENTOS
                       WHERE SGR_ID = %s AND ORIGEN = %s""",
                    (sgr_id, "FACTURA"),
                )
                movimiento_registro = cursor.fetchone()

                if movimiento_registro is None:
                    importar_factura(cursor, sgr, actualizado_por)
                    importados += 1
                elif movimiento_registro[1] != estado:
                    reflejar_estado(cursor, movimiento_registro[0], estado)
                    actualizados += 1
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
            "actualizados": actualizados,
            "sin_cambios": sin_cambios,
            "ignorados": ignorados,
            "actualizado_por": actualizado_por,
        },
    )
