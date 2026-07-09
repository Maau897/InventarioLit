# Inventario General INER

App en Streamlit para operar el inventario LIT y el listado Frontera.

## Fuentes actuales

- `LIT`: usa la base oficial sembrada en `inventory_seed_entries`; se reconstruye desde `Inventario_de_materiales_LIT_01_07_2026.xlsx`.
- `Frontera`: queda vacio por ahora y se usara para capturas nuevas cuando se implemente ese flujo.
- Los Excel quedan solo como respaldo para reconstruir la base oficial.

Los archivos Excel no se suben al repositorio. En Streamlit Cloud la app debe leer la base oficial desde Supabase.

## Ejecutar local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy en Streamlit Cloud

1. Sube solo el codigo a GitHub.
2. No subas inventarios, formatos, credenciales ni respaldos locales.
3. Corre `supabase/inventory_schema.sql` en Supabase.
4. Sube la base oficial a Supabase con el script de semilla.
5. Configura secrets en Streamlit Cloud.

Para sembrar `LIT` desde el Excel oficial y dejar `Frontera` vacio:

```powershell
$env:SUPABASE_URL="https://tu-proyecto.supabase.co"
$env:SUPABASE_KEY="tu-service-role-key"
python scripts\build_official_inventory_seed.py --all
```

En la app, al seleccionar `LIT`, se carga solo el scope `lit` construido desde el formulario oficial de LIT. Al seleccionar `Frontera`, se muestra el inventario capturado para ese scope.

Para sembrar solo una:

```powershell
python scripts\build_official_inventory_seed.py --lit
python scripts\build_official_inventory_seed.py --frontera
```

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

La app primero intenta leer `inventory_seed_entries`. Si no hay registros para el inventario activo, muestra la opcion de reconstruir desde Excel como respaldo.

La pestaña `Editar catalogo` permite corregir nombres ambiguos, marca, catalogo, categoria, unidad y ubicacion sin modificar cantidades.
