# Cupo vehicular de colaboradores

Servicio de cuenta corriente por colaborador expuesto como lambda local ejecutable con Serverless Framework.

## Requisitos

- Node 18+ (probado con Node 26 + Serverless v3 + serverless-offline v8)
- Python 3 con `venv`
- Docker (para Postgres)

## Inicializacion

```bash
# 1. DB real: Postgres en contenedor 
docker compose up -d db
psql -h localhost -U cupo -d cupo -f sql/01_tablas.sql
psql -h localhost -U cupo -d cupo -f sql/02_seed.sql
psql -h localhost -U cupo -d cupo -f sql/03_seed_admins.sql

# 2. Dependencias (credenciales salen de .env; para otra DB edita .env)
cp .env.example .env   # el zip no incluye .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install

# 3. Lambda en local (con el venv en el PATH para que offline use ese python3)
PATH="$PWD/.venv/bin:$PATH" npx serverless offline start --httpPort 3000
```

Probar los 6 endpoints (escenario completo, admin de ejemplo `1701234567`):

```bash
BASE=http://localhost:3000
ADMIN=1701234567
CED=0912345678

# 1. Crear colaborador -> 201 (repetir -> 409)
curl -X POST $BASE/colaboradores -H 'Content-Type: application/json' \
  -d "{\"cedula\":\"$CED\",\"cupo_mensual\":200}"

# 2. Actualizar cupo 200 -> 300 -> 200 (deja historial, no mueve saldo)
curl -X PUT $BASE/colaboradores/$CED/cupo -H 'Content-Type: application/json' \
  -d "{\"cupo_mensual\":300,\"actualizado_por\":\"$ADMIN\"}"

# 3. Acreditar dos veces -> saldo 300 -> 600
curl -X POST $BASE/colaboradores/$CED/acreditaciones -H 'Content-Type: application/json' \
  -d "{\"actualizado_por\":\"$ADMIN\"}"

# 4. Registrar factura 50 -> 201 en Pendiente, saldo 550.
#    Con total 9999 -> 422; mismo numero otra vez -> 409
curl -X POST $BASE/facturas -H 'Content-Type: application/json' \
  -d "{\"cedula\":\"$CED\",\"numero_factura\":\"001-001-000000999\",\"ruc_proveedor\":\"1790012345001\",\"total\":50,\"registrado_por\":\"$ADMIN\"}"

# 5. Sync GasClub -> importa GC-000901 y GC-000944, ignora el resto
curl -X POST $BASE/sincronizaciones/gasclub -H 'Content-Type: application/json' \
  -d "{\"actualizado_por\":\"$ADMIN\"}"

# 6. Sync facturas -> importa las del seed, alinea estados.
#    Para probar aprobacion: UPDATE manual + re-sync
psql -h localhost -U cupo -d cupo -c "UPDATE sgr_facturas SET estado='Aprobado' WHERE numero_factura='001-001-000000999'"
curl -X POST $BASE/sincronizaciones/facturas -H 'Content-Type: application/json' \
  -d "{\"actualizado_por\":\"$ADMIN\"}"
# -> actualizados 1; tu movimiento queda Aprobado

# Verificar saldo contra el libro mayor (deben coincidir)
psql -h localhost -U cupo -d cupo -c "SELECT cedula, cupo_mensual, saldo FROM app_colaboradores"
psql -h localhost -U cupo -d cupo -c "SELECT tipo, origen, monto, saldo_resultante, referencia, estado FROM app_movimientos ORDER BY id"
```

## Datos de prueba (Faker)

`scripts/generar_datos.py` suma filas convincentes (nombres con Faker,
cédulas/RUC/facturas con formato local) sin borrar nada. Faker va en
`requirements-dev.txt` para no engordar la lambda.

```bash
pip install -r requirements-dev.txt
# 50 colaboradores con 4 facturas y 6 consumos cada uno, reproducible
.venv/bin/python scripts/generar_datos.py --colaboradores 50 --facturas 4 --gasclub 6 --seed 42
# solo filas SGR para colaboradores ya registrados (ideal para probar syncs)
.venv/bin/python scripts/generar_datos.py --solo-sgr --facturas 10 --seed 7
```

Parámetros (defaults pensados para una corrida rápida):

| Parámetro | Default | Qué hace |
|---|---|---|
| `--admins` | 3 | administradores nuevos (nombre con Faker) |
| `--colaboradores` | 20 | colaboradores nuevos (saldo 0, cupo al azar) |
| `--facturas` | 3 | facturas SGR por colaborador |
| `--gasclub` | 3 | consumos GasClub por colaborador |
| `--cupo-min` / `--cupo-max` | 100 / 500 | rango del cupo mensual |
| `--total-min` / `--total-max` | 10 / 250 | rango de totales (facturas y GasClub) |
| `--p-pendiente` | 0.4 | probabilidad de factura `Pendiente` (resto `Aprobado`) |
| `--seed` | ninguno | semilla: mismo seed, misma data |
| `--solo-sgr` | apagado | no crea admins ni colaboradores, solo filas SGR para los ya registrados |

