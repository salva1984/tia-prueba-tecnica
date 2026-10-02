"""Genera datos de prueba convincentes en la DB 

Uso:
  .venv/bin/python scripts/generar_datos.py --colaboradores 50 --facturas 4 --gasclub 6
  .venv/bin/python scripts/generar_datos.py --solo-sgr --facturas 10 --seed 7
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Permite `python scripts/generar_datos.py` desde la raiz (sys.path[0]
# seria scripts/ y no encontraria el paquete app).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker

from app.db import get_conn

fake = Faker("es_ES")


def cedula_ec(rand):
    # Cedula de 10 digitos: 2 de provincia (01-24) + 8 al azar.
    return f"{rand.randint(1, 24):02d}{rand.randint(0, 99999999):08d}"


def cedula_unica(rand, usadas):
    while True:
        ced = cedula_ec(rand)
        if ced not in usadas:
            usadas.add(ced)
            return ced


def max_id(cur, tabla):
    cur.execute(f"SELECT COALESCE(MAX(ID), 0) FROM {tabla}")
    return cur.fetchone()[0]


def cargar_admins(cur, n, desde_id, usadas, rand):
    filas = []
    for i in range(n):
        filas.append(
            (desde_id + i, cedula_unica(rand, usadas), fake.name(), date.today())
        )
    cur.executemany(
        "INSERT INTO APP_ADMINISTRADORES (ID, CEDULA, NOMBRE, FECHA_CREACION)"
        " VALUES (%s, %s, %s, %s)",
        filas,
    )
    return len(filas)


def cargar_colaboradores(cur, n, desde_id, usadas, rand, cupo_min, cupo_max):
    filas = []
    cedulas = []
    for i in range(n):
        ced = cedula_unica(rand, usadas)
        cedulas.append(ced)
        filas.append(
            (
                desde_id + i,
                ced,
                round(rand.uniform(cupo_min, cupo_max), 2),
                0,
                date.today(),
                date.today(),
            )
        )
    cur.executemany(
        """INSERT INTO APP_COLABORADORES
           (ID, CEDULA, CUPO_MENSUAL, SALDO, FECHA_CREACION, FECHA_ACTUALIZACION)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        filas,
    )
    return cedulas


def numero_factura_unico(rand, usados):
    while True:
        num = (
            f"{rand.randint(1, 5):03d}-{rand.randint(1, 9):03d}-"
            f"{rand.randint(0, 9999999):09d}"
        )
        if num not in usados:
            usados.add(num)
            return num


def cargar_facturas(
    cur, cedulas, n_cada, desde_id, numeros, rand, total_min, total_max, p_pendiente
):
    filas = []
    proximo = desde_id
    for ced in cedulas:
        for _ in range(n_cada):
            ruc = f"{cedula_ec(rand)}001"[:13]
            total = round(rand.uniform(total_min, total_max), 2)
            estado = "Pendiente" if rand.random() < p_pendiente else "Aprobado"
            fecha = date.today() - timedelta(days=rand.randint(0, 90))
            filas.append(
                (
                    proximo,
                    ced,
                    numero_factura_unico(rand, numeros),
                    ruc,
                    total,
                    fecha,
                    estado,
                )
            )
            proximo += 1
    cur.executemany(
        """INSERT INTO SGR_FACTURAS
           (ID, CEDULA, NUMERO_FACTURA, RUC_PROVEEDOR, TOTAL, FECHA, ESTADO)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        filas,
    )
    return len(filas)


def referencia_gc_unica(rand, usadas):
    while True:
        ref = f"GC-{rand.randint(1, 999999):06d}"
        if ref not in usadas:
            usadas.add(ref)
            return ref


def cargar_gasclub(cur, cedulas, n_cada, desde_id, refs, rand, total_min, total_max):
    filas = []
    proximo = desde_id
    for ced in cedulas:
        for _ in range(n_cada):
            total = round(rand.uniform(5, total_max), 2)
            fecha = date.today() - timedelta(days=rand.randint(0, 90))
            filas.append((proximo, ced, referencia_gc_unica(rand, refs), total, fecha))
            proximo += 1
    cur.executemany(
        """INSERT INTO SGR_GASCLUB_GASTOS
           (ID, CEDULA, REFERENCIA, TOTAL, FECHA)
           VALUES (%s, %s, %s, %s, %s)""",
        filas,
    )
    return len(filas)


def conjunto(cur, tabla, columna):
    cur.execute(f"SELECT {columna} FROM {tabla}")
    return set(fila[0] for fila in cur.fetchall())


def main():
    ap = argparse.ArgumentParser(description="Genera datos de prueba en la DB.")
    ap.add_argument("--admins", type=int, default=3)
    ap.add_argument("--colaboradores", type=int, default=20)
    ap.add_argument(
        "--facturas", type=int, default=3, help="facturas SGR por colaborador"
    )
    ap.add_argument(
        "--gasclub", type=int, default=3, help="consumos GasClub por colaborador"
    )
    ap.add_argument("--cupo-min", type=float, default=100.0)
    ap.add_argument("--cupo-max", type=float, default=500.0)
    ap.add_argument("--total-min", type=float, default=10.0)
    ap.add_argument("--total-max", type=float, default=250.0)
    ap.add_argument(
        "--p-pendiente",
        type=float,
        default=0.4,
        help="probabilidad de factura Pendiente (0-1)",
    )
    ap.add_argument(
        "--seed", type=int, default=None, help="semilla para repetir la misma data"
    )
    ap.add_argument(
        "--solo-sgr",
        action="store_true",
        help="solo filas SGR para colaboradores ya registrados",
    )
    args = ap.parse_args()

    rand = random.Random(args.seed)
    if args.seed is not None:
        Faker.seed(args.seed)

    conn = get_conn()
    try:
        cur = conn.cursor()
        if args.solo_sgr:
            cur.execute("SELECT CEDULA FROM APP_COLABORADORES")
            cedulas = [fila[0] for fila in cur.fetchall()]
            n_admin = 0
        else:
            # Solo aqui se generan cedulas nuevas, solo aqui hace falta
            # saber cuales estan usadas.
            cedulas_usadas = conjunto(cur, "APP_COLABORADORES", "CEDULA") | conjunto(
                cur, "APP_ADMINISTRADORES", "CEDULA"
            )
            n_admin = cargar_admins(
                cur,
                args.admins,
                max_id(cur, "APP_ADMINISTRADORES") + 1,
                cedulas_usadas,
                rand,
            )
            cedulas = cargar_colaboradores(
                cur,
                args.colaboradores,
                max_id(cur, "APP_COLABORADORES") + 1,
                cedulas_usadas,
                rand,
                args.cupo_min,
                args.cupo_max,
            )

        numeros = conjunto(cur, "SGR_FACTURAS", "NUMERO_FACTURA")
        refs = conjunto(cur, "SGR_GASCLUB_GASTOS", "REFERENCIA")
        n_fac = cargar_facturas(
            cur,
            cedulas,
            args.facturas,
            max_id(cur, "SGR_FACTURAS") + 1,
            numeros,
            rand,
            args.total_min,
            args.total_max,
            args.p_pendiente,
        )
        n_gc = cargar_gasclub(
            cur,
            cedulas,
            args.gasclub,
            max_id(cur, "SGR_GASCLUB_GASTOS") + 1,
            refs,
            rand,
            args.total_min,
            args.total_max,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        f"admins: {n_admin}, colaboradores: {len(cedulas)}, "
        f"facturas: {n_fac}, gasclub: {n_gc}"
    )


if __name__ == "__main__":
    main()
