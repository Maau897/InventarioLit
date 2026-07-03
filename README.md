# Inventario General INER

App en Streamlit para operar el inventario LIT y el listado Frontera.

## Fuentes actuales

- `LIT`: usa el conteo real de la hoja `JUL 26` del archivo de indicadores de almacenes.
- `LIT`: usa el inventario de recuperacion solo como plantilla/catalogo; no suma existencia.
- `Frontera`: usa el listado federal/local como fuente separada.

Los archivos Excel no se suben al repositorio. En local se pueden leer desde la carpeta del proyecto; en Streamlit Cloud se cargan desde la barra lateral.

## Ejecutar local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy en Streamlit Cloud

1. Sube solo el codigo a GitHub.
2. No subas inventarios, formatos, credenciales ni respaldos locales.
3. Configura secrets en Streamlit Cloud si se usara Supabase.
4. En la app desplegada, sube los Excel desde la barra lateral cuando la app los pida.

## Archivos excluidos

El `.gitignore` excluye:

- `.streamlit/`
- `secrets.toml`
- credenciales `.json`
- Excel: `.xlsx`, `.xlsm`, `.xls`
- formatos `.docx`
- `data/`
- `outputs/`
- `node_modules/`

## Supabase

El esquema base esta en `supabase/inventory_schema.sql`.

Si se activa persistencia remota, configura en secrets:

```toml
supabase_url = "..."
supabase_key = "..."
```
