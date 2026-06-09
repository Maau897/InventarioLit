from pathlib import Path

import pandas as pd
import streamlit as st

from inventory_app.config import (
    DEFAULT_SCOPE,
    INVENTORY_SCOPES,
    MATERIALS_WORKBOOK_PATH,
    RECOVERY_WORKBOOK_PATH,
    SHEET_NAME_DEFAULTS,
)
from inventory_app.excel_loader import (
    BASE_COLUMNS,
    build_catalog_options,
    build_inventory_snapshot,
    build_product_search_links,
    clean_count_results_sheet,
    clean_registry_sheet,
    combine_catalogs,
    enrich_inventory_with_counts,
    harmonize_transaction_keys,
    load_material_inventory_frames,
    load_workbook_frames,
)
from inventory_app.google_sheets_loader import (
    get_google_sheet_settings,
    load_google_sheet_frames,
    load_sheet_dataframe,
)
from inventory_app.repositories import MOVEMENT_COLUMNS, get_repository


st.set_page_config(page_title="Inventario General INER", layout="wide")

ENTRY_COLUMNS = [
    "id_registro",
    "codigo",
    "descripcion",
    "catalogo",
    "marca",
    "lote",
    "cantidad",
    "unidad",
    "caducidad",
    "ubicacion",
    "categoria",
    "fecha",
    "responsable",
    "temperatura",
    "observaciones",
    "verificado_por",
]

SUMMARY_COLUMNS = [
    "codigo",
    "descripcion",
    "marca",
    "categoria",
    "ubicacion",
    "lote",
    "caducidad",
    "entrada",
    "salida",
    "existencia",
]

NEGATIVE_COLUMNS = [
    "codigo",
    "codigo_local",
    "descripcion",
    "marca",
    "categoria",
    "ubicacion",
    "lote",
    "caducidad",
    "entrada",
    "salida",
    "existencia",
]

TABLE_COLUMNS = [
    "id_registro",
    "codigo",
    "descripcion",
    "marca",
    "catalogo",
    "lote",
    "caducidad",
    "cantidad",
    "unidad",
    "responsable",
    "fecha",
]

EDITABLE_MOVEMENT_COLUMNS = [
    "movement_uid",
    "id_registro",
    "codigo",
    "descripcion",
    "catalogo",
    "marca",
    "lote",
    "cantidad",
    "unidad",
    "caducidad",
    "ubicacion",
    "categoria",
    "fecha",
    "responsable",
    "temperatura",
    "observaciones",
    "verificado_por",
]


def init_state() -> None:
    if "selected_code" not in st.session_state:
        st.session_state.selected_code = ""


def prefill_values(selected_label: str, catalog_df: pd.DataFrame) -> dict[str, object]:
    defaults = {column: "" for column in ENTRY_COLUMNS}
    defaults["cantidad"] = 1
    defaults["fecha"] = pd.Timestamp.today().date()
    defaults["categoria"] = "REACTIVO"
    if selected_label == "Nuevo insumo" or catalog_df.empty:
        return defaults

    selected_code = selected_label.split(" - ", 1)[0]
    match = catalog_df.loc[catalog_df["codigo"] == selected_code]
    if match.empty:
        return defaults

    row = match.iloc[0]
    defaults.update(
        {
            "id_registro": row.get("id_registro", ""),
            "codigo": row.get("codigo", ""),
            "descripcion": row.get("descripcion", ""),
            "catalogo": row.get("catalogo", ""),
            "marca": row.get("marca", ""),
            "lote": row.get("lote", ""),
            "unidad": row.get("unidad", ""),
            "caducidad": row.get("caducidad", ""),
            "ubicacion": row.get("ubicacion", ""),
            "categoria": row.get("categoria", "OTRO"),
        }
    )
    return defaults


def render_full_table(title: str, df: pd.DataFrame, search_key: str) -> None:
    st.subheader(title)
    if df.empty:
        st.info("No hay datos disponibles en esta tabla.")
        return

    search = st.text_input(f"Buscar en {title.lower()}", key=search_key)
    filtered = df.copy()
    if search:
        pattern = search.strip().lower()
        filtered = filtered.loc[
            filtered.astype(str)
            .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
            .any(axis=1)
        ]
    st.dataframe(filtered, use_container_width=True, hide_index=True)


def order_columns(df: pd.DataFrame, preferred: list[str]) -> list[str]:
    existing_preferred = [column for column in preferred if column in df.columns]
    remaining = [column for column in df.columns if column not in existing_preferred]
    return existing_preferred + remaining


def rename_display_columns(df: pd.DataFrame, rename_map: dict[str, str]) -> pd.DataFrame:
    available = {key: value for key, value in rename_map.items() if key in df.columns}
    return df.rename(columns=available)


def render_movement_form(
    movement_type: str,
    catalog_df: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    title = "Registrar entrada" if movement_type == "entrada" else "Registrar salida"
    st.subheader(title)
    st.caption("Este movimiento se guarda en la app y se suma al inventario del scope activo.")

    if movement_type == "salida":
        search_catalog = st.text_input(
            "Buscar por catalogo",
            key=f"search_catalog_{inventory_scope}_{movement_type}",
            help="Busca por codigo, catalogo, descripcion o marca.",
        )
        filtered_catalog = catalog_df.copy()
        if search_catalog.strip():
            pattern = search_catalog.strip().lower()
            filtered_catalog = filtered_catalog.loc[
                filtered_catalog[["codigo", "catalogo", "descripcion", "marca"]]
                .astype(str)
                .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
                .any(axis=1)
            ]
        option_source = filtered_catalog if not filtered_catalog.empty else catalog_df
    else:
        option_source = catalog_df

    selected_label = st.selectbox(
        "Selecciona un insumo",
        options=build_catalog_options(option_source),
        key=f"selector_{inventory_scope}_{movement_type}",
    )
    defaults = prefill_values(selected_label, catalog_df)

    with st.form(f"form_{inventory_scope}_{movement_type}", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            id_registro = st.text_input(
                "ID de entrada" if movement_type == "entrada" else "ID de salida",
                value=str(defaults["id_registro"]),
            )
            codigo = st.text_input("Codigo", value=str(defaults["codigo"]))
            descripcion = st.text_input("Descripcion", value=str(defaults["descripcion"]))
            catalogo = st.text_input("Catalogo", value=str(defaults["catalogo"]))
            marca = st.text_input("Marca", value=str(defaults["marca"]))
        with col2:
            lote = st.text_input("Lote", value=str(defaults["lote"]))
            cantidad = st.number_input("Cantidad", min_value=0.0, step=1.0, value=float(defaults["cantidad"]))
            unidad = st.text_input("Unidad", value=str(defaults["unidad"]))
            caducidad = st.text_input(
                "Caducidad",
                value="" if pd.isna(defaults["caducidad"]) else str(defaults["caducidad"]),
            )
        with col3:
            ubicacion = st.text_input("Ubicacion", value=str(defaults["ubicacion"]))
            category_options = ["REACTIVO", "MATERIAL", "OTRO"]
            default_category = str(defaults["categoria"]).upper()
            if default_category not in category_options:
                default_category = "OTRO"
            categoria = st.selectbox(
                "Categoria",
                options=category_options,
                index=category_options.index(default_category),
            )
            fecha = st.date_input("Fecha", value=defaults["fecha"])
            responsable = st.text_input("Responsable", value=str(defaults["responsable"]))
        extra_col1, extra_col2 = st.columns(2)
        with extra_col1:
            temperatura = st.text_input(
                "Temperatura (C)" if movement_type == "entrada" else "Temperatura (opcional)",
                value=str(defaults["temperatura"]),
            )
            verificado_por = st.text_input("Verificado por (opcional)", value=str(defaults["verificado_por"]))
        with extra_col2:
            observaciones = st.text_area("Observaciones", value=str(defaults["observaciones"]), height=120)

        submitted = st.form_submit_button("Guardar movimiento", use_container_width=True)
        if submitted:
            errors = []
            if not codigo.strip():
                errors.append("El codigo es obligatorio.")
            if not descripcion.strip():
                errors.append("La descripcion es obligatoria.")
            if cantidad <= 0:
                errors.append("La cantidad debe ser mayor a cero.")
            if not responsable.strip():
                errors.append("El responsable es obligatorio.")
            if movement_type == "entrada" and not temperatura.strip():
                errors.append("La temperatura es obligatoria para el formato de entrada.")

            if errors:
                for error in errors:
                    st.error(error)
            else:
                repository.save_movement(
                    {
                        "inventory_scope": inventory_scope,
                        "movement_type": movement_type,
                        "id_registro": id_registro.strip(),
                        "codigo": codigo.strip(),
                        "descripcion": descripcion.strip(),
                        "catalogo": catalogo.strip(),
                        "marca": marca.strip(),
                        "lote": lote.strip(),
                        "cantidad": cantidad,
                        "unidad": unidad.strip(),
                        "caducidad": caducidad.strip(),
                        "ubicacion": ubicacion.strip(),
                        "categoria": categoria.strip(),
                        "fecha": pd.to_datetime(fecha).strftime("%Y-%m-%d"),
                        "responsable": responsable.strip(),
                        "temperatura": temperatura.strip(),
                        "observaciones": observaciones.strip(),
                        "verificado_por": verificado_por.strip(),
                    }
                )
                st.success("Movimiento guardado correctamente.")
                st.rerun()


def render_editable_captured_rows(
    selected_code: str,
    inventory_scope: str,
    app_movements: pd.DataFrame,
    repository,
) -> None:
    scope_rows = app_movements.loc[
        (app_movements["inventory_scope"] == inventory_scope) & (app_movements["codigo"] == selected_code)
    ].copy()
    if scope_rows.empty:
        st.info("No hay movimientos capturados en la app para este catalogo.")
        return

    for movement_type, title in [("entrada", "Entradas capturadas"), ("salida", "Salidas capturadas")]:
        subset = scope_rows.loc[scope_rows["movement_type"] == movement_type].copy()
        st.markdown(f"#### {title}")
        if subset.empty:
            st.caption("No hay registros editables de este tipo para el catalogo seleccionado.")
            continue

        editor_source = subset[EDITABLE_MOVEMENT_COLUMNS].copy().set_index("movement_uid")
        edited = st.data_editor(
            editor_source,
            hide_index=True,
            use_container_width=True,
            key=f"editor_{inventory_scope}_{movement_type}_{selected_code}",
        )
        if st.button(
            f"Guardar cambios de {movement_type}",
            key=f"save_editor_{inventory_scope}_{movement_type}_{selected_code}",
            use_container_width=True,
        ):
            updated = edited.reset_index().rename(columns={"index": "movement_uid"})
            updated["inventory_scope"] = inventory_scope
            updated["movement_type"] = movement_type
            updated["captured_at"] = updated["movement_uid"].map(
                subset.set_index("movement_uid")["captured_at"].to_dict()
            )
            updated["fecha"] = pd.to_datetime(updated["fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
            updated["cantidad"] = pd.to_numeric(updated["cantidad"], errors="coerce").fillna(0)
            repository.upsert_movements(updated[MOVEMENT_COLUMNS])
            st.success(f"Se actualizaron las {movement_type}s capturadas.")
            st.rerun()


def render_catalog_search(
    general_inventory_df: pd.DataFrame,
    app_movements: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    st.subheader("Buscador por catalogo")
    st.caption(
        "Busca por catalogo, codigo, descripcion o marca. Desde aqui puedes localizar el activo y editar movimientos capturados para corregir negativos."
    )
    search = st.text_input("Buscar activo", key=f"catalog_search_{inventory_scope}")
    if not search:
        st.info("Escribe un catalogo, descripcion o marca para buscar.")
        return

    pattern = search.strip().lower()
    matches = general_inventory_df.loc[
        general_inventory_df.astype(str)
        .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
        .any(axis=1)
    ].copy()

    if matches.empty:
        st.warning("No encontre coincidencias.")
        return

    options = [f"{row['codigo']} - {row['descripcion']}" for _, row in matches.head(50).iterrows()]
    selected = st.selectbox("Selecciona un activo", options=options, key=f"selected_asset_{inventory_scope}")
    selected_code = selected.split(" - ", 1)[0]
    row = matches.loc[matches["codigo"] == selected_code].iloc[0]
    links = build_product_search_links(row)

    card_left, card_right = st.columns([2, 1])
    with card_left:
        st.markdown("### Ficha del activo")
        st.markdown(f"**Catalogo / Codigo:** {row['codigo']}")
        st.markdown(f"**Descripcion:** {row['descripcion']}")
        st.markdown(f"**Marca:** {row['marca']}")
        st.markdown(f"**Categoria:** {row.get('categoria', '')}")
        st.markdown(f"**Ubicacion:** {row.get('ubicacion', '')}")
        st.markdown(f"**Lote:** {row.get('lote', '')}")
        st.markdown(f"**Caducidad:** {row.get('caducidad', '')}")
        st.markdown(f"**Entradas acumuladas:** {row.get('entrada', '')}")
        st.markdown(f"**Salidas acumuladas:** {row.get('salida', '')}")
        st.markdown(f"**Existencia estimada:** {row.get('existencia', '')}")
    with card_right:
        st.markdown("### Links")
        st.markdown(f"[Buscar en Google]({links['google']})")
        st.markdown(f"[Buscar proveedor / producto]({links['proveedor']})")

    render_editable_captured_rows(selected_code, inventory_scope, app_movements, repository)


def load_inventory_bundle(
    inventory_scope: str,
    recovery_workbook_source,
    materials_workbook_source,
    sheet_settings: dict[str, str],
    repository,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    if inventory_scope == "recuperacion":
        google_frames = load_google_sheet_frames(sheet_settings)
        if recovery_workbook_source is not None:
            excel_frames = load_workbook_frames(recovery_workbook_source)
            frames = {
                "entradas": pd.concat(
                    [
                        harmonize_transaction_keys(google_frames["entradas"]),
                        harmonize_transaction_keys(excel_frames["entradas"]),
                    ],
                    ignore_index=True,
                ),
                "salidas": pd.concat(
                    [
                        harmonize_transaction_keys(google_frames["salidas"]),
                        harmonize_transaction_keys(excel_frames["salidas"]),
                    ],
                    ignore_index=True,
                ),
                "catalogo": combine_catalogs(
                    google_frames.get("catalogo", pd.DataFrame()),
                    excel_frames.get("catalogo", pd.DataFrame()),
                ),
            }
        else:
            frames = google_frames
        registry_df = clean_registry_sheet(load_sheet_dataframe(sheet_settings["spreadsheet_id"], "Registro"))
        results_df = clean_count_results_sheet(
            load_sheet_dataframe(sheet_settings["spreadsheet_id"], "Resultados de conteos")
        )
        return frames, registry_df, results_df

    if sheet_settings.get("spreadsheet_id", "").strip():
        frames = load_google_sheet_frames(sheet_settings)
        return frames, pd.DataFrame(), pd.DataFrame()

    seed_df = repository.load_seed_entries(inventory_scope)
    if not seed_df.empty:
        seed_entries = seed_df.rename(
            columns={
                "source_label": "responsable",
                "loaded_at": "fecha",
            }
        ).copy()
        for column in BASE_COLUMNS:
            if column not in seed_entries.columns:
                seed_entries[column] = None
        seed_entries = seed_entries[BASE_COLUMNS].copy()
        seed_entries["fecha"] = pd.to_datetime(seed_entries["fecha"], errors="coerce")
        frames = {
            "entradas": seed_entries,
            "salidas": pd.DataFrame(columns=BASE_COLUMNS),
            "catalogo": seed_entries[
                [
                    "codigo",
                    "codigo_local",
                    "descripcion",
                    "catalogo",
                    "marca",
                    "lote",
                    "unidad",
                    "caducidad",
                    "ubicacion",
                    "categoria",
                ]
            ].drop_duplicates("codigo"),
        }
        return frames, pd.DataFrame(), pd.DataFrame()

    if materials_workbook_source is None:
        raise RuntimeError(
            f"No hay Google Sheets configurado para `{INVENTORY_SCOPES[inventory_scope]}`, no hay semilla en Supabase y tampoco existe el Excel local."
        )

    frames = load_material_inventory_frames(materials_workbook_source, inventory_scope)
    return frames, pd.DataFrame(), pd.DataFrame()


def explain_load_error(exc: Exception, inventory_scope: str) -> None:
    st.error(f"No pude cargar el inventario `{INVENTORY_SCOPES[inventory_scope]}`: {exc}")
    if inventory_scope == "recuperacion":
        st.info("Verifica credenciales de Google Sheets, permiso compartido y, si quieres histórico adicional, que el Excel local exista.")
    else:
        st.info("Configura un Google Sheet para ese inventario o deja disponible el Excel local en esta máquina.")


def resolve_workbook_source(local_path: str):
    path = Path(local_path)
    if path.exists():
        return path
    return None


def main() -> None:
    init_state()
    st.title("Inventario General INER")
    st.caption("Inventarios operativos por scope: recuperacion, avimex y federal/general.")

    repository = get_repository()

    inventory_scope = st.sidebar.radio(
        "Inventario activo",
        options=list(INVENTORY_SCOPES.keys()),
        index=list(INVENTORY_SCOPES.keys()).index(DEFAULT_SCOPE),
        format_func=lambda key: INVENTORY_SCOPES[key],
    )

    recovery_workbook_path = st.sidebar.text_input(
        "Excel de recuperacion",
        value=str(RECOVERY_WORKBOOK_PATH),
    )
    materials_workbook_path = st.sidebar.text_input(
        "Excel Avimex/Federal",
        value=str(MATERIALS_WORKBOOK_PATH),
    )

    sheet_settings = get_google_sheet_settings(inventory_scope)

    st.sidebar.markdown("**Fuente configurada**")
    if inventory_scope == "recuperacion":
        st.sidebar.caption("Google Sheets obligatorio. Excel local opcional para histórico adicional.")
    else:
        st.sidebar.caption("Google Sheets recomendado. Excel local solo como fallback de desarrollo.")
    st.sidebar.text_input(
        "Spreadsheet ID",
        value=sheet_settings.get("spreadsheet_id", ""),
        disabled=True,
    )
    st.sidebar.text_input(
        "Pestana catalogo",
        value=sheet_settings.get("catalog_sheet", SHEET_NAME_DEFAULTS["catalog_sheet"]),
        disabled=True,
    )
    st.sidebar.text_input(
        "Pestana entradas",
        value=sheet_settings.get("entries_sheet", SHEET_NAME_DEFAULTS["entries_sheet"]),
        disabled=True,
    )
    st.sidebar.text_input(
        "Pestana salidas",
        value=sheet_settings.get("exits_sheet", SHEET_NAME_DEFAULTS["exits_sheet"]),
        disabled=True,
    )

    recovery_workbook_source = None
    materials_workbook_source = None
    if inventory_scope == "recuperacion":
        recovery_workbook_source = resolve_workbook_source(recovery_workbook_path)
    else:
        materials_workbook_source = resolve_workbook_source(materials_workbook_path)

    try:
        frames, registry_df, results_df = load_inventory_bundle(
            inventory_scope,
            recovery_workbook_source,
            materials_workbook_source,
            sheet_settings,
            repository,
        )
    except Exception as exc:
        explain_load_error(exc, inventory_scope)
        return

    app_movements = repository.load_movements()
    scope_movements = app_movements.loc[app_movements["inventory_scope"] == inventory_scope].copy()
    inventory_df, entry_df, exit_df, catalog_df = build_inventory_snapshot(
        frames["entradas"],
        frames["salidas"],
        scope_movements,
        catalog_df=frames.get("catalogo"),
    )

    if inventory_scope == "recuperacion":
        general_inventory_df = enrich_inventory_with_counts(inventory_df, registry_df, results_df)
    else:
        general_inventory_df = inventory_df.copy()

    st.markdown(f"### Inventario: {INVENTORY_SCOPES[inventory_scope]}")
    if inventory_scope == "recuperacion":
        if recovery_workbook_source is None:
            st.caption("Fuente: Google Sheets de recuperacion.")
            st.info("No se encontro el Excel local de recuperacion. La app sigue operando solo con Google Sheets.")
        else:
            st.caption("Fuente: Google Sheets + Excel local de recuperacion.")
    elif inventory_scope == "avimex":
        if sheet_settings.get("spreadsheet_id", "").strip():
            st.caption("Fuente: Google Sheets de Avimex.")
        else:
            st.caption("Fuente: hoja `Avimex` enriquecida con `Inventario Final` cuando faltan claves.")
    else:
        if sheet_settings.get("spreadsheet_id", "").strip():
            st.caption("Fuente: Google Sheets de Federal/general.")
        else:
            st.caption("Fuente: `Presupuesto federal`, `Reactivos` e `Inventario Final` para arrancar el inventario general/federal.")

    total_items = len(general_inventory_df)
    total_stock = float(general_inventory_df["existencia"].fillna(0).sum()) if not general_inventory_df.empty else 0
    total_entries = float(entry_df["cantidad"].fillna(0).sum()) if not entry_df.empty else 0
    total_exits = float(exit_df["cantidad"].fillna(0).sum()) if not exit_df.empty else 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Claves activas", f"{total_items}")
    kpi2.metric("Existencia total", f"{total_stock:,.0f}")
    kpi3.metric("Entradas acumuladas", f"{total_entries:,.0f}")
    kpi4.metric("Salidas acumuladas", f"{total_exits:,.0f}")

    resumen_tab, negativos_tab, buscador_tab, recepcion_tab, salidas_tab, entrada_form_tab, salida_form_tab = st.tabs(
        [
            "Resumen general",
            "Negativos por revisar",
            "Buscador catalogo",
            "Recepcion",
            "Salidas",
            "Registrar entrada",
            "Registrar salida",
        ]
    )

    with resumen_tab:
        st.subheader("Inventario general")
        categoria_filtro = st.multiselect(
            "Filtrar por categoria",
            options=sorted(general_inventory_df["categoria"].dropna().unique().tolist()),
            key=f"cat_filter_{inventory_scope}",
        )
        search = st.text_input(
            "Buscar por codigo, descripcion, marca o ubicacion",
            key=f"search_inventario_{inventory_scope}",
        )
        filtered = general_inventory_df.copy()
        if categoria_filtro:
            filtered = filtered.loc[filtered["categoria"].isin(categoria_filtro)]
        if search:
            pattern = search.strip().lower()
            filtered = filtered.loc[
                filtered.astype(str)
                .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
                .any(axis=1)
            ]
        visible_columns = [column for column in SUMMARY_COLUMNS if column in filtered.columns]
        st.dataframe(
            filtered[order_columns(filtered, visible_columns)],
            use_container_width=True,
            hide_index=True,
        )

    with negativos_tab:
        st.subheader("Negativos por revisar")
        negativos_df = general_inventory_df.loc[general_inventory_df["existencia"] < 0].copy()
        if negativos_df.empty:
            st.success("No hay claves con existencia negativa.")
        else:
            visible_columns = [column for column in NEGATIVE_COLUMNS if column in negativos_df.columns]
            st.dataframe(
                negativos_df[order_columns(negativos_df, visible_columns)].sort_values("existencia"),
                use_container_width=True,
                hide_index=True,
            )

    with buscador_tab:
        render_catalog_search(general_inventory_df, app_movements, repository, inventory_scope)

    with recepcion_tab:
        recepcion_df = entry_df.sort_values("fecha", ascending=False, na_position="last").copy()
        visible_columns = [column for column in TABLE_COLUMNS + ["temperatura"] if column in recepcion_df.columns]
        render_full_table(
            "Recepcion",
            rename_display_columns(
                recepcion_df[order_columns(recepcion_df, visible_columns)],
                {
                    "responsable": "Recibio",
                },
            ),
            f"search_recepcion_{inventory_scope}",
        )

    with salidas_tab:
        salidas_df = exit_df.sort_values("fecha", ascending=False, na_position="last").copy()
        visible_columns = [column for column in TABLE_COLUMNS if column in salidas_df.columns]
        render_full_table(
            "Salidas",
            rename_display_columns(
                salidas_df[order_columns(salidas_df, visible_columns)],
                {
                    "responsable": "Iniciales",
                },
            ),
            f"search_salidas_{inventory_scope}",
        )

    with entrada_form_tab:
        render_movement_form("entrada", catalog_df, repository, inventory_scope)

    with salida_form_tab:
        render_movement_form("salida", catalog_df, repository, inventory_scope)


if __name__ == "__main__":
    main()
