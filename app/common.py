import json
from decimal import Decimal, InvalidOperation

from psycopg2.extensions import cursor as Cursor


def response(status, payload):
    """Arma la respuesta HTTP que API Gateway / serverless-offline esperan."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }


def path_params(event):
    params = (event or {}).get("pathParameters")
    if isinstance(params, dict):
        return params
    return {}


def parse_event_body(event):
    if not event:
        return {}
    raw = event.get("body")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


class ValidationError(Exception):
    def __init__(self, errores: list[str]):
        super().__init__("; ".join(errores))
        self.errores = errores


def validar_cedula(cedula: str, campo: str = "cedula") -> str:
    if not cedula:
        raise ValidationError([f"{campo} es requerida"])
    errores = []
    if not cedula.isdigit():
        errores.append(f"{campo} debe contener solo numeros")
    if len(cedula) < 10 or len(cedula) > 13:
        errores.append(f"{campo} debe tener entre 10 y 13 caracteres")
    if errores:
        raise ValidationError(errores)
    return cedula


def validar_monto(monto_raw, campo: str = "cupo_mensual") -> Decimal:

    if monto_raw is None:
        raise ValidationError([f"{campo} es requerido"])
    if isinstance(monto_raw, str) and monto_raw.strip() == "":
        raise ValidationError([f"{campo} es requerido"])
    try:
        monto = Decimal(str(monto_raw))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError([f"{campo} debe ser un numero"])
    if monto <= 0:
        raise ValidationError([f"{campo} debe ser mayor que 0"])
    return monto


def validar_texto(valor, campo: str, solo_numeros: bool = False) -> str:
    if valor is None:
        raise ValidationError([f"{campo} es requerido"])
    texto = str(valor).strip()
    if texto == "":
        raise ValidationError([f"{campo} es requerido"])
    if solo_numeros and not texto.isdigit():
        raise ValidationError([f"{campo} debe contener solo numeros"])
    return texto


def colaborador_existe(cedula: str, cur: Cursor) -> bool:
    cur.execute("SELECT ID FROM APP_COLABORADORES WHERE CEDULA = %s", (cedula,))
    return cur.fetchone() is not None


class NoEncontrado(Exception):
    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class Conflicto(Exception):
    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


def obtener_colaborador(cedula: str, cur: Cursor) -> dict:
    cur.execute(
        "SELECT CUPO_MENSUAL, SALDO FROM APP_COLABORADORES WHERE CEDULA = %s",
        (cedula,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise NoEncontrado("colaborador no existe")
    cupo_mensual, saldo = fila
    return {"cupo_mensual": cupo_mensual, "saldo": saldo}


def admin_existe(cedula: str, cur: Cursor) -> bool:
    cur.execute("SELECT ID FROM APP_ADMINISTRADORES WHERE CEDULA = %s", (cedula,))
    return cur.fetchone() is not None


def factura_registrada(cedula: str, numero_factura: str, cur: Cursor) -> bool:
    cur.execute(
        """SELECT ID FROM APP_MOVIMIENTOS
           WHERE CEDULA = %s AND ORIGEN = %s AND REFERENCIA = %s""",
        (cedula, "FACTURA", numero_factura),
    )
    if cur.fetchone() is not None:
        return True
    cur.execute(
        "SELECT ID FROM SGR_FACTURAS WHERE CEDULA = %s AND NUMERO_FACTURA = %s",
        (cedula, numero_factura),
    )
    return cur.fetchone() is not None


def siguiente_id(cur: Cursor, tabla: str) -> int:
    cur.execute(f"SELECT COALESCE(MAX(ID), 0) + 1 FROM {tabla}")
    return cur.fetchone()[0]


def mover_saldo(cur: Cursor, cedula: str, balance_change) -> Decimal:
    cur.execute(
        """UPDATE APP_COLABORADORES
           SET SALDO = SALDO + %s, FECHA_ACTUALIZACION = CURRENT_DATE
           WHERE CEDULA = %s RETURNING SALDO""",
        (balance_change, cedula),
    )
    return cur.fetchone()[0]
