from datetime import date

from app.common import (
    NoEncontrado,
    ValidationError,
    admin_existe,
    obtener_colaborador,
    parse_event_body,
    path_params,
    response,
    mover_saldo,
    siguiente_id,
    validar_cedula,
)
from app.db import get_conn


def handler(event, context):
    """POST /colaboradores/{cedula}/acreditaciones — body: {actualizado_por}."""
    data = parse_event_body(event)
    ruta = path_params(event)

    try:
        cedula_colaborador = validar_cedula(str(ruta.get("cedula", "")).strip())
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

        try:
            colab = obtener_colaborador(cedula_colaborador, cursor)
        except NoEncontrado as e:
            return response(404, {"error": e.mensaje})
        cupo, saldo_anterior = colab["cupo_mensual"], colab["saldo"]

        hoy = date.today()

        saldo_nuevo = mover_saldo(cursor, cedula_colaborador, cupo)
        cursor.execute(
            """INSERT INTO APP_MOVIMIENTOS
               (ID, CEDULA, TIPO, ORIGEN, MONTO, SALDO_RESULTANTE, REFERENCIA,
                SGR_ID, RUC_PROVEEDOR, ESTADO, REGISTRADO_POR, FECHA)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                siguiente_id(cursor, "APP_MOVIMIENTOS"),
                cedula_colaborador,
                "ACREDITACION",
                "CUPO",
                cupo,
                saldo_nuevo,
                "ACREDITACION",
                None,
                None,
                None,
                actualizado_por,
                hoy,
            ),
        )
        conn.commit()
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
            "cedula": cedula_colaborador,
            "acreditado": float(cupo),
            "saldo_anterior": float(saldo_anterior),
            "saldo_nuevo": float(saldo_nuevo),
            "actualizado_por": actualizado_por,
        },
    )
