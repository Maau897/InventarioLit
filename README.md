# Inventario INER

App en Streamlit para operar tres inventarios:

- `recuperacion`: Google Sheets + Excel local de recuperacion
- `avimex`: Excel `Inventario_material_y_reactivos_21_Enero_2026.xlsx`
- `federal`: base inicial desde `Presupuesto federal`, `Reactivos` e `Inventario Final`

## Ejecutar local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue en Streamlit Cloud

1. Sube este repositorio a GitHub sin los archivos sensibles.
2. En Streamlit Cloud configura manualmente los secrets de Google Sheets y, si aplica, los de Supabase.
3. En la app desplegada:
   - `recuperacion` usa Google Sheets y necesita además subir el Excel de recuperación en la barra lateral.
   - `avimex` y `federal` usan el Excel `Inventario_material_y_reactivos_21_Enero_2026.xlsx`, también vía upload en la barra lateral.

## Datos sensibles excluidos

No se deben subir al repositorio:

- credenciales de Google Cloud
- archivos `.xlsx`, `.xlsm`, `.xls`
- formatos `.docx`
- respaldos CSV locales

## Supabase

El esquema base está en `supabase/inventory_schema.sql`.
Ejecuta ese script antes de activar persistencia remota.
