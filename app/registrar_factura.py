from datetime import date

from app.common import (
    Conflicto,
    NoEncontrado,
    ValidationError,
    admin_existe,
    factura_registrada,
    mover_saldo,
    obtener_colaborador,
    parse_event_body,
    response,
    siguiente_id,
    validar_cedula,
    validar_monto,
    validar_texto,
)
from app.db import get_conn


def handler(event, context):
    """POST /facturas — body: {cedula, numero_factura, ruc_proveedor,
    total, registrado_por}."""
    data = parse_event_body(event)

    try:
        cedula = validar_cedula(str(data.get("cedula", "")).strip())
        numero = validar_texto(data.get("numero_factura"), "numero_factura")
        ruc = validar_texto(
            data.get("ruc_proveedor"), "ruc_proveedor", solo_numeros=True
        )
        total = validar_monto(data.get("total"), "total")
        registrado_por = validar_cedula(
            str(data.get("registrado_por", "")).strip(), "registrado_por"
        )
    except ValidationError as e:
        return response(400, {"errores": e.errores})

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        if not admin_existe(registrado_por, cursor):
            return response(403, {"error": "administrador no registrado"})

        try:
            colab = obtener_colaborador(cedula, cursor)
        except NoEncontrado as e:
            return response(404, {"error": e.mensaje})
        saldo = colab["saldo"]

        if factura_registrada(cedula, numero, cursor):
            raise Conflicto("factura ya registrada")

        if total > saldo:
            return response(
                422,
                {
                    "error": "saldo insuficiente",
                    "total": float(total),
                    "saldo_disponible": float(saldo),
                },
            )

        hoy = date.today()

        sgr_id = siguiente_id(cursor, "SGR_FACTURAS")

        cursor.execute(
            """INSERT INTO SGR_FACTURAS
               (ID, CEDULA, NUMERO_FACTURA, RUC_PROVEEDOR, TOTAL, FECHA, ESTADO)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (sgr_id, cedula, numero, ruc, total, hoy, "Pendiente"),
        )

        saldo_nuevo = mover_saldo(cursor, cedula, -total)
        mov_id = siguiente_id(cursor, "APP_MOVIMIENTOS")
        cursor.execute(
            """INSERT INTO APP_MOVIMIENTOS
               (ID, CEDULA, TIPO, ORIGEN, MONTO, SALDO_RESULTANTE, REFERENCIA,
                SGR_ID, RUC_PROVEEDOR, ESTADO, REGISTRADO_POR, FECHA)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                mov_id,
                cedula,
                "GASTO",
                "FACTURA",
                total,
                saldo_nuevo,
                numero,
                sgr_id,
                ruc,
                "Pendiente",
                registrado_por,
                hoy,
            ),
        )
        conn.commit()
    except Conflicto as e:
        if conn is not None:
            conn.rollback()
        return response(409, {"error": e.mensaje})
    except Exception as exc:  # error de DB
        if conn is not None:
            conn.rollback()
        return response(500, {"error": str(exc)})
    finally:
        if conn is not None:
            conn.close()

    return response(
        201,
        {
            "id": mov_id,
            "sgr_id": sgr_id,
            "cedula": cedula,
            "numero_factura": numero,
            "total": float(total),
            "saldo_anterior": float(saldo),
            "saldo_nuevo": float(saldo_nuevo),
            "estado": "Pendiente",
            "registrado_por": registrado_por,
        },
    )
