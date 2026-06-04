# Inventario General INER

## Lo que ya detectamos en el Excel

- La hoja `Entradas` es la mejor fuente para altas y recepcion de insumos.
- La hoja `Salidas` registra consumos o retiros.
- La hoja `Inventario` calcula existencia con la formula `Entrada - Salida`.
- En `Entradas` hay muchas columnas vacias de mas; para la app conviene trabajar solo con las 12 columnas utiles.
- Los formatos Word de entrada y salida piden casi los mismos campos del Excel, asi que podemos reutilizar una sola captura y luego generar el formato final.

## Recomendacion de arquitectura

- Seguir con `Streamlit` para el MVP.
- Usar `Supabase` como respaldo y fuente transaccional en cuanto validemos el flujo.
- Mantener el Excel como fuente historica inicial, no como motor principal de captura.

## Flujo propuesto

1. Cargar el inventario historico desde el Excel general.
2. Consolidar catalogo por `codigo`.
3. Registrar nuevas entradas o salidas desde formularios editables.
4. Guardar cada movimiento en una tabla de movimientos.
5. Recalcular existencias en tiempo real.
6. Generar el formato diario de entradas y salidas para impresion o cierre.
7. En una siguiente fase, exportar a Word o PDF con el mismo formato institucional.

## Modelo de datos minimo

### Catalogo base

- `codigo`
- `descripcion`
- `catalogo`
- `marca`
- `unidad`
- `categoria`

### Movimientos

- `movement_type`
- `codigo`
- `descripcion`
- `catalogo`
- `marca`
- `lote`
- `cantidad`
- `unidad`
- `caducidad`
- `ubicacion`
- `categoria`
- `fecha`
- `responsable`
- `captured_at`

## Implementacion por fases

### Fase 1

- Lectura del Excel general.
- Vista consolidada del inventario.
- Formularios para entradas y salidas.
- Respaldo local en CSV.

### Fase 2

- Tablas en Supabase.
- Autenticacion por usuario.
- Bitacora de cambios.
- Reportes filtrables por fecha, categoria y responsable.

### Fase 3

- Generacion automatica del formato final de entradas/salidas.
- Alertas de caducidad y stock bajo.
- Modulo de conteos fisicos y conciliacion.
