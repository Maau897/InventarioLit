from pathlib import Path
from io import BytesIO
import os
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from inventory_app.config import (
    DEFAULT_SCOPE,
    INVENTORY_SCOPES,
    LIT_OFFICIAL_WORKBOOK_PATH,
    MATERIALS_WORKBOOK_PATH,
    SHEET_NAME_DEFAULTS,
)
from inventory_app.excel_loader import (
    BASE_COLUMNS,
    CANONICAL_CATALOG_COLUMN,
    CANONICAL_DESCRIPTION_COLUMN,
    ITEM_KEY_COLUMN,
    RAW_ITEM_KEY_COLUMN,
    build_catalog_options,
    build_inventory_snapshot,
    build_product_search_links,
    ensure_item_key,
    harmonize_transaction_keys,
    load_lit_official_inventory_frames,
    load_seed_inventory_frames,
    normalize_match_key,
    parse_mixed_datetime_series,
    parse_single_datetime,
)
from inventory_app.repositories import MOVEMENT_COLUMNS, PHYSICAL_COUNT_COLUMNS, REGULARIZATION_COLUMNS, get_repository
from inventory_app.supabase_users import (
    actualizar_rol_usuario,
    aprobar_usuario,
    autenticar_usuario,
    configure_supabase_users,
    crear_admin_inicial,
    eliminar_usuario,
    listar_eventos_auditoria,
    listar_usuarios,
    obtener_usuarios_pendientes,
    registrar_evento_auditoria,
    registrar_usuario,
    supabase_users_enabled,
)
from inventory_app.config import LOCAL_DATA_DIR


st.set_page_config(page_title="Inventario General INER", layout="wide")

ROLES_USUARIO = ["captura", "responsable", "auditor", "calidad", "admin"]

ENTRY_COLUMNS = [
    "id_registro",
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
    "catalogo",
    "descripcion",
    "marca",
    "categoria",
    "ubicacion",
    "lote",
    "caducidad",
    "fecha_recepcion",
    "entrada",
    "salida",
    "existencia",
]

NEGATIVE_COLUMNS = [
    ITEM_KEY_COLUMN,
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

NEGATIVE_DIAGNOSTIC_COLUMNS = [
    ITEM_KEY_COLUMN,
    "codigo",
    "catalogo",
    "descripcion",
    "marca",
    "entrada",
    "salida",
    "existencia",
    "catalog_variants_count",
    "description_family_count",
    "same_norm_entry_count",
    "same_norm_exit_count",
    "recommended_action",
    "diagnosis_flags",
]

TABLE_COLUMNS = [
    "id_registro",
    "catalogo",
    "descripcion",
    "marca",
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
    "catalogo",
    "descripcion",
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

MOVEMENT_ADMIN_COLUMNS = [
    "movement_uid",
    "movement_type",
    "id_registro",
    "catalogo",
    "descripcion",
    "marca",
    "lote",
    "cantidad",
    "unidad",
    "ubicacion",
    "categoria",
    "fecha",
    "responsable",
    "observaciones",
    "captured_at",
]

NEGATIVE_REVIEW_COLUMNS = [
    "id_registro",
    "catalogo",
    "descripcion",
    "marca",
    "lote",
    "cantidad",
    "unidad",
    "caducidad",
    "ubicacion",
    "categoria",
    "fecha",
    "responsable",
]

CONFLICT_COLUMNS = [
    "created_at",
    "inventory_scope",
    "codigo_reportado",
    "codigo_sugerido",
    "descripcion",
    "marca",
    "motivo",
    "detalle",
]

CONFLICTS_PATH = LOCAL_DATA_DIR / "conflictos_homologacion.csv"
REGULARIZATION_DISPLAY_COLUMNS = [
    "tipo_regularizacion",
    "fecha_corte",
    "fecha_validacion",
    "catalogo",
    "descripcion",
    "marca",
    "lote",
    "cantidad",
    "unidad",
    "caducidad",
    "ubicacion",
    "categoria",
    "soporte_disponible",
    "folio_origen",
    "comentario_regularizacion",
    "validado_por",
    "inventory_scope",
]

PHYSICAL_COUNT_DISPLAY_COLUMNS = [
    "fecha_conteo",
    "catalogo",
    "descripcion",
    "marca",
    "lote",
    "unidad",
    "ubicacion",
    "categoria",
    "existencia_anterior",
    "conteo_fisico",
    "verificacion_fisica",
    "conteos_empatan",
    "diferencia",
    "ajuste_aplicado",
    "contador",
    "verificador",
    "observaciones",
    "captured_at",
]

HIDDEN_DISPLAY_COLUMNS = [
    "codigo",
    "codigo_local",
]


def get_config_value(secret_key: str, env_key: str, default: Any = "") -> Any:
    try:
        return st.secrets.get(secret_key, os.getenv(env_key, default))
    except Exception:
        return os.getenv(env_key, default)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "on"}
    return bool(value)


def configure_users_backend() -> None:
    configure_supabase_users(
        url=str(get_config_value("supabase_url", "SUPABASE_URL", "")),
        key=str(get_config_value("supabase_key", "SUPABASE_KEY", "")),
        enabled=as_bool(get_config_value("use_supabase_users", "USE_SUPABASE_USERS", False)),
        table_name=str(get_config_value("supabase_users_table", "SUPABASE_USERS_TABLE", "usuarios_app")),
        audit_table_name=str(get_config_value("supabase_audit_table", "SUPABASE_AUDIT_TABLE", "inventario_auditoria")),
    )

    admin_email = str(get_config_value("admin_email", "ADMIN_EMAIL", "")).strip()
    admin_password = str(get_config_value("admin_password", "ADMIN_PASSWORD", "")).strip()
    if supabase_users_enabled() and admin_email and admin_password:
        try:
            crear_admin_inicial(admin_email, admin_password)
        except Exception:
            pass


def normalize_user_role(rol: Any, es_admin: bool = False) -> str:
    if es_admin:
        return "admin"
    normalized = str(rol or "captura").strip().lower()
    return normalized if normalized in ROLES_USUARIO else "captura"


def init_state() -> None:
    if "selected_code" not in st.session_state:
        st.session_state.selected_code = ""
    defaults = {
        "autenticado": False,
        "usuario_email": "",
        "es_admin": False,
        "rol_usuario": "captura",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def log_activity(accion: str, detalle: str = "") -> None:
    if not supabase_users_enabled():
        return
    try:
        registrar_evento_auditoria(
            email=str(st.session_state.get("usuario_email", "")).strip(),
            accion=accion,
            detalle=detalle,
        )
    except Exception:
        pass


def render_auth_screen() -> None:
    st.title("Acceso al inventario")
    st.caption("Ingresa con tu usuario autorizado para usar el sistema.")

    if not supabase_users_enabled():
        st.error("La autenticacion no esta configurada en esta app.")
        st.info("Activa `use_supabase_users` y configura `supabase_url`, `supabase_key` y `supabase_users_table` en secrets.")
        st.stop()

    login_tab, register_tab = st.tabs(["Iniciar sesion", "Crear cuenta"])

    with login_tab:
        email_login = st.text_input("Correo", key="login_email")
        password_login = st.text_input("Contrasena", type="password", key="login_password")
        if st.button("Ingresar", use_container_width=True):
            try:
                result = autenticar_usuario(email_login, password_login, normalize_user_role)
                if result["ok"]:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_email"] = result["email"]
                    st.session_state["es_admin"] = result["es_admin"]
                    st.session_state["rol_usuario"] = result.get("rol", "captura")
                    log_activity("inicio_sesion", "Ingreso a Inventario")
                    st.rerun()
                else:
                    st.error(result["mensaje"])
            except Exception as exc:
                st.error(f"No se pudo iniciar sesion: {exc}")

    with register_tab:
        email_register = st.text_input("Correo institucional o personal", key="register_email")
        password_register = st.text_input("Contrasena", type="password", key="register_password")
        password_register_2 = st.text_input("Confirmar contrasena", type="password", key="register_password_2")
        requested_role = st.selectbox(
            "Perfil solicitado",
            ["captura", "responsable", "auditor", "calidad"],
            format_func=lambda value: value.capitalize(),
            key="register_role",
        )
        if st.button("Crear cuenta", use_container_width=True):
            try:
                if not email_register.strip() or not password_register:
                    st.warning("Completa correo y contrasena.")
                elif password_register != password_register_2:
                    st.warning("Las contrasenas no coinciden.")
                else:
                    registrar_usuario(email_register, password_register, requested_role)
                    st.success("Cuenta creada. Queda pendiente de aprobacion.")
            except Exception as exc:
                st.error(f"No se pudo crear la cuenta: {exc}")


def render_user_sidebar() -> None:
    st.sidebar.write(f"Sesion: `{st.session_state.get('usuario_email', '')}`")
    st.sidebar.write(f"Perfil: `{st.session_state.get('rol_usuario', 'captura')}`")
    if st.sidebar.button("Cerrar sesion", use_container_width=True):
        log_activity("cerrar_sesion", "Salida de Inventario")
        st.session_state["autenticado"] = False
        st.session_state["usuario_email"] = ""
        st.session_state["es_admin"] = False
        st.session_state["rol_usuario"] = "captura"
        st.rerun()


def render_user_admin_sidebar() -> None:
    if not st.session_state.get("es_admin", False) or not supabase_users_enabled():
        return

    st.sidebar.divider()
    st.sidebar.subheader("Administracion de usuarios")
    try:
        pending_users = obtener_usuarios_pendientes()
        st.sidebar.markdown("**Solicitudes pendientes**")
        if pending_users:
            for user_id, email, registered_at in pending_users:
                st.sidebar.write(f"{email} - {registered_at}")
                approval_role = st.sidebar.selectbox(
                    f"Rol para {email}",
                    ROLES_USUARIO,
                    index=ROLES_USUARIO.index("captura"),
                    format_func=lambda value: value.capitalize(),
                    key=f"approval_role_{user_id}",
                )
                if st.sidebar.button("Aprobar", key=f"approve_{user_id}", use_container_width=True):
                    aprobar_usuario(user_id, approval_role)
                    log_activity("aprobar_usuario", f"{email} -> {approval_role}")
                    st.sidebar.success(f"Usuario {email} aprobado.")
                    st.rerun()
        else:
            st.sidebar.caption("No hay usuarios pendientes.")

        st.sidebar.markdown("**Usuarios activos**")
        approved_users = [row for row in listar_usuarios() if row[2] == 1]
        admin_count = sum(1 for row in approved_users if row[3] == 1)
        if approved_users:
            for user_id, email, _, _, role, _ in approved_users:
                new_role = st.sidebar.selectbox(
                    email,
                    ROLES_USUARIO,
                    index=ROLES_USUARIO.index(role if role in ROLES_USUARIO else "captura"),
                    format_func=lambda value: value.capitalize(),
                    key=f"role_user_{user_id}",
                )
                if st.sidebar.button("Actualizar rol", key=f"update_role_{user_id}", use_container_width=True):
                    actualizar_rol_usuario(user_id, new_role)
                    log_activity("actualizar_rol", f"{email} -> {new_role}")
                    st.sidebar.success(f"Rol de {email} actualizado.")
                    st.rerun()
                can_delete_user = email != str(st.session_state.get("usuario_email", "")).strip().lower()
                would_remove_last_admin = role == "admin" and admin_count <= 1
                if st.sidebar.button("Quitar acceso", key=f"delete_user_{user_id}", use_container_width=True):
                    if not can_delete_user:
                        st.sidebar.warning("No puedes quitar tu propio acceso desde aqui.")
                    elif would_remove_last_admin:
                        st.sidebar.warning("No puedes quitar al ultimo admin activo.")
                    else:
                        eliminar_usuario(user_id)
                        log_activity("quitar_acceso", email)
                        st.sidebar.success(f"Se quito el acceso de {email}.")
                        st.rerun()
        else:
            st.sidebar.caption("No hay usuarios aprobados.")

        with st.sidebar.expander("Historial de actividad", expanded=False):
            try:
                events = listar_eventos_auditoria(limit=40)
                if events:
                    for event in events:
                        st.write(f"{event.get('created_at', '')} - {event.get('email', '')}")
                        st.caption(f"{event.get('accion', '')}: {event.get('detalle', '')}")
                else:
                    st.caption("Sin actividad registrada todavia.")
            except Exception:
                st.caption("El historial aun no esta disponible.")
    except Exception as exc:
        st.sidebar.error(f"No se pudo cargar la administracion de usuarios: {exc}")


def get_item_key(row: pd.Series) -> str:
    return str(row.get(ITEM_KEY_COLUMN, "") or row.get("catalogo", "") or row.get("codigo", "")).strip()


def technical_code(catalogo: object, descripcion: object = "") -> str:
    value = str(catalogo or "").strip()
    if value:
        return value
    return str(descripcion or "").strip() or "SIN CATALOGO"


def required_db_text(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def safe_float(value: object, fallback: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return fallback
    return float(parsed)


def filter_by_item_key(df: pd.DataFrame, item_key: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    prepared = ensure_item_key(df)
    return prepared.loc[prepared[ITEM_KEY_COLUMN] == item_key].copy()


def normalize_text_key(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def add_diagnostic_keys(df: pd.DataFrame) -> pd.DataFrame:
    prepared = ensure_item_key(df)
    for column in ["catalogo", "codigo", "descripcion", "marca", ITEM_KEY_COLUMN]:
        if column not in prepared.columns:
            prepared[column] = ""
    prepared["catalog_norm"] = prepared["catalogo"].map(normalize_match_key)
    prepared["code_norm"] = prepared["codigo"].map(normalize_match_key)
    prepared["item_norm"] = prepared[ITEM_KEY_COLUMN].map(normalize_match_key)
    prepared["description_brand_key"] = (
        prepared["descripcion"].map(normalize_text_key) + "||" + prepared["marca"].map(normalize_text_key)
    )
    return prepared


def build_negative_diagnostics(
    inventory_df: pd.DataFrame,
    entry_df: pd.DataFrame,
    exit_df: pd.DataFrame,
) -> pd.DataFrame:
    inventory = add_diagnostic_keys(inventory_df)
    entries = add_diagnostic_keys(entry_df)
    exits = add_diagnostic_keys(exit_df)
    negatives = inventory.loc[inventory["existencia"] < 0].copy()
    if negatives.empty:
        return negatives

    rows: list[dict[str, object]] = []
    for _, row in negatives.iterrows():
        item_norm = row.get("item_norm", "")
        desc_brand_key = row.get("description_brand_key", "")
        item_key = str(row.get(ITEM_KEY_COLUMN, "") or "").strip()
        family_inventory = inventory.loc[inventory["description_brand_key"] == desc_brand_key].copy()
        same_norm_inventory = inventory.loc[
            (inventory["item_norm"] == item_norm) | (inventory["catalog_norm"] == row.get("catalog_norm", ""))
        ].copy()
        same_norm_entries = entries.loc[
            (entries["item_norm"] == item_norm) | (entries["catalog_norm"] == row.get("catalog_norm", ""))
        ].copy()
        same_norm_exits = exits.loc[
            (exits["item_norm"] == item_norm) | (exits["catalog_norm"] == row.get("catalog_norm", ""))
        ].copy()

        raw_variants = sorted(
            {
                str(value).strip()
                for value in pd.concat(
                    [
                        same_norm_inventory["catalogo"],
                        same_norm_entries["catalogo"],
                        same_norm_exits["catalogo"],
                    ],
                    ignore_index=True,
                ).fillna("")
                if str(value).strip() != ""
            }
        )
        family_keys = sorted({get_item_key(candidate) for _, candidate in family_inventory.iterrows() if get_item_key(candidate)})

        flags: list[str] = []
        if len(raw_variants) > 1:
            flags.append("variantes_catalogo")
        if len(family_keys) > 1:
            flags.append("misma_descripcion_marca")
        if float(row.get("entrada", 0) or 0) <= 0 and len(same_norm_entries) > 0:
            flags.append("entrada_en_variante_hermana")
        if float(row.get("entrada", 0) or 0) <= 0 and float(row.get("salida", 0) or 0) > 0:
            flags.append("sin_entrada_directa")
        if float(row.get("salida", 0) or 0) > float(row.get("entrada", 0) or 0) and len(same_norm_entries) > 0:
            flags.append("salida_supera_entrada_local")
        if item_key == "T-200-Y":
            flags = [flag for flag in flags if flag not in {"variantes_catalogo", "misma_descripcion_marca"}]
            flags.append("negativo_real_confirmado")

        recommended_action = "revisar_manual"
        if "negativo_real_confirmado" in flags:
            recommended_action = "negativo_real"
        elif "variantes_catalogo" in flags or "misma_descripcion_marca" in flags:
            recommended_action = "revisar_homologacion"
        elif "sin_entrada_directa" in flags or "entrada_en_variante_hermana" in flags:
            recommended_action = "buscar_entrada_faltante"
        elif float(row.get("salida", 0) or 0) > 0:
            recommended_action = "revisar_salidas"

        record = row.to_dict()
        record.update(
            {
                "catalog_variants_count": len(raw_variants),
                "catalog_variants": " | ".join(raw_variants),
                "description_family_count": len(family_keys),
                "description_family_keys": " | ".join(family_keys),
                "same_norm_entry_count": len(same_norm_entries),
                "same_norm_exit_count": len(same_norm_exits),
                "recommended_action": recommended_action,
                "diagnosis_flags": " | ".join(flags) if flags else "sin_bandera",
            }
        )
        rows.append(record)

    return pd.DataFrame(rows).sort_values(["recommended_action", "existencia"])


def build_related_variant_rows(
    selected_item_key: str,
    inventory_df: pd.DataFrame,
    entry_df: pd.DataFrame,
    exit_df: pd.DataFrame,
) -> pd.DataFrame:
    inventory = add_diagnostic_keys(inventory_df)
    entries = add_diagnostic_keys(entry_df)
    exits = add_diagnostic_keys(exit_df)
    selected_inventory = filter_by_item_key(inventory, selected_item_key)
    if selected_inventory.empty:
        return pd.DataFrame()

    selected_row = selected_inventory.iloc[0]
    item_norm = selected_row.get("item_norm", "")
    desc_brand_key = selected_row.get("description_brand_key", "")

    inventory_matches = inventory.loc[
        (inventory["item_norm"] == item_norm)
        | (inventory["catalog_norm"] == selected_row.get("catalog_norm", ""))
        | (inventory["description_brand_key"] == desc_brand_key)
    ].copy()
    inventory_matches["source_type"] = "inventario_actual"

    entry_matches = entries.loc[
        (entries["item_norm"] == item_norm)
        | (entries["catalog_norm"] == selected_row.get("catalog_norm", ""))
        | (entries["description_brand_key"] == desc_brand_key)
    ].copy()
    entry_matches["source_type"] = "entrada_fuente"

    exit_matches = exits.loc[
        (exits["item_norm"] == item_norm)
        | (exits["catalog_norm"] == selected_row.get("catalog_norm", ""))
        | (exits["description_brand_key"] == desc_brand_key)
    ].copy()
    exit_matches["source_type"] = "salida_fuente"

    combined = pd.concat([inventory_matches, entry_matches, exit_matches], ignore_index=True, sort=False)
    if combined.empty:
        return combined
    combined = apply_canonical_display(combined)
    preferred = [
        "source_type",
        ITEM_KEY_COLUMN,
        RAW_ITEM_KEY_COLUMN,
        "codigo",
        "catalogo",
        "catalogo_original",
        "descripcion",
        "descripcion_original",
        "marca",
        "lote",
        "cantidad",
        "unidad",
        "fecha",
        "caducidad",
        "ubicacion",
        "categoria",
        "entrada",
        "salida",
        "existencia",
    ]
    return sort_by_existing_columns(
        combined[order_columns(combined, preferred)],
        ["source_type", "catalogo", "codigo", "lote", "fecha"],
        na_position="last",
    )


def prefill_values(selected_label: str, catalog_df: pd.DataFrame) -> dict[str, object]:
    defaults = {column: "" for column in ENTRY_COLUMNS}
    defaults["cantidad"] = 1
    defaults["fecha"] = pd.Timestamp.today().date()
    defaults["categoria"] = "REACTIVO"
    if selected_label == "Nuevo insumo" or catalog_df.empty:
        return defaults

    selected_code = selected_label.split(" - ", 1)[0]
    match = filter_by_item_key(catalog_df, selected_code)
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


def prefill_values_from_catalog(catalog_text: str, catalog_df: pd.DataFrame) -> tuple[dict[str, object], int]:
    defaults = {column: "" for column in ENTRY_COLUMNS}
    defaults["cantidad"] = 1
    defaults["fecha"] = pd.Timestamp.today().date()
    defaults["categoria"] = "REACTIVO"
    if catalog_df.empty or not catalog_text.strip():
        return defaults, 0

    prepared = ensure_item_key(catalog_df)
    target = normalize_match_key(catalog_text)
    matches = prepared.loc[
        (prepared["catalogo"].map(normalize_match_key) == target)
        | (prepared[CANONICAL_CATALOG_COLUMN].map(normalize_match_key) == target)
        | (prepared[ITEM_KEY_COLUMN].map(normalize_match_key) == target)
    ].copy()
    if matches.empty:
        return defaults, 0

    row = matches.iloc[0]
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
    return defaults, len(matches)


def render_full_table(title: str, df: pd.DataFrame, search_key: str) -> None:
    st.subheader(title)
    if df.empty:
        st.info("No hay datos disponibles en esta tabla.")
        return

    df = df.drop(columns=[column for column in HIDDEN_DISPLAY_COLUMNS if column in df.columns])
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


def sort_by_existing_columns(
    df: pd.DataFrame,
    columns: list[str],
    ascending=True,
    na_position: str = "last",
) -> pd.DataFrame:
    sort_columns = [column for column in columns if column in df.columns]
    if not sort_columns:
        return df
    return df.sort_values(sort_columns, ascending=ascending, na_position=na_position)


def rename_display_columns(df: pd.DataFrame, rename_map: dict[str, str]) -> pd.DataFrame:
    available = {key: value for key, value in rename_map.items() if key in df.columns}
    return df.rename(columns=available)


def hide_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[column for column in HIDDEN_DISPLAY_COLUMNS if column in df.columns])


def apply_canonical_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    prepared = ensure_item_key(df)
    prepared = prepared.copy()
    prepared["catalogo_original"] = prepared.get("catalogo", "")
    prepared["descripcion_original"] = prepared.get("descripcion", "")
    if CANONICAL_CATALOG_COLUMN in prepared.columns:
        prepared["catalogo"] = prepared[CANONICAL_CATALOG_COLUMN].where(
            prepared[CANONICAL_CATALOG_COLUMN].fillna("").astype(str).str.strip() != "",
            prepared["catalogo"],
        )
    if CANONICAL_DESCRIPTION_COLUMN in prepared.columns:
        prepared["descripcion"] = prepared[CANONICAL_DESCRIPTION_COLUMN].where(
            prepared[CANONICAL_DESCRIPTION_COLUMN].fillna("").astype(str).str.strip() != "",
            prepared["descripcion"],
        )
    return prepared


def normalize_tab_key(value: str) -> str:
    return value.lower().replace(" ", "_")


def get_scope_filter_values(inventory_scope: str) -> list[str]:
    if inventory_scope == "lit":
        return ["lit"]
    if inventory_scope == "frontera":
        return ["frontera"]
    return [inventory_scope]


def filter_app_scope_rows(app_movements: pd.DataFrame, inventory_scope: str, selected_code: str | None = None) -> pd.DataFrame:
    if app_movements.empty:
        return pd.DataFrame(columns=app_movements.columns)
    filtered = app_movements.loc[app_movements["inventory_scope"].isin(get_scope_filter_values(inventory_scope))].copy()
    if "is_voided" in filtered.columns:
        filtered = filtered.loc[~filtered["is_voided"].fillna(False).astype(bool)].copy()
    filtered = ensure_item_key(filtered)
    if selected_code is not None:
        filtered = filtered.loc[filtered[ITEM_KEY_COLUMN] == selected_code].copy()
    return filtered


def filter_all_app_scope_rows(app_movements: pd.DataFrame, inventory_scope: str) -> pd.DataFrame:
    if app_movements.empty:
        return pd.DataFrame(columns=MOVEMENT_COLUMNS)
    return app_movements.loc[app_movements["inventory_scope"].isin(get_scope_filter_values(inventory_scope))].copy()


def complete_movement_columns(updated: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    completed = updated.copy()
    original_by_uid = original.set_index("movement_uid") if "movement_uid" in original.columns else pd.DataFrame()
    for column in MOVEMENT_COLUMNS:
        if column not in completed.columns:
            if not original_by_uid.empty and column in original_by_uid.columns:
                completed[column] = completed["movement_uid"].map(original_by_uid[column].to_dict())
            else:
                completed[column] = None
    return completed[MOVEMENT_COLUMNS]


def load_conflict_flags() -> pd.DataFrame:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFLICTS_PATH.exists():
        return pd.DataFrame(columns=CONFLICT_COLUMNS)
    df = pd.read_csv(CONFLICTS_PATH)
    for column in CONFLICT_COLUMNS:
        if column not in df.columns:
            df[column] = None
    return df[CONFLICT_COLUMNS]


def save_conflict_flag(payload: dict[str, object]) -> None:
    existing = load_conflict_flags()
    updated = pd.concat([existing, pd.DataFrame([payload])], ignore_index=True)
    updated.to_csv(CONFLICTS_PATH, index=False)


def render_negative_item_card(row: pd.Series) -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Catalogo:** {row.get('catalogo', '')}")
        st.markdown(f"**Descripcion:** {row.get('descripcion', '')}")
        st.markdown(f"**Marca:** {row.get('marca', '')}")
    with col2:
        st.markdown(f"**Categoria:** {row.get('categoria', '')}")
        st.markdown(f"**Ubicacion:** {row.get('ubicacion', '')}")
        st.markdown(f"**Lote:** {row.get('lote', '')}")
        st.markdown(f"**Caducidad:** {row.get('caducidad', '')}")
    with col3:
        st.metric("Entradas", f"{float(row.get('entrada', 0) or 0):,.0f}")
        st.metric("Salidas", f"{float(row.get('salida', 0) or 0):,.0f}")
        st.metric("Diferencia final", f"{float(row.get('existencia', 0) or 0):,.0f}")


def render_add_missing_entry_form(row: pd.Series, repository, inventory_scope: str) -> None:
    st.markdown("#### Agregar entrada faltante")
    with st.form(f"missing_entry_{inventory_scope}_{row['codigo']}"):
        form_col1, form_col2, form_col3 = st.columns(3)
        with form_col1:
            catalogo = st.text_input("Catalogo", value=str(row.get("catalogo", "")))
            descripcion = st.text_input("Descripcion", value=str(row.get("descripcion", "")))
            marca = st.text_input("Marca", value=str(row.get("marca", "")))
        with form_col2:
            lote = st.text_input("Lote", value=str(row.get("lote", "")))
            cantidad = st.number_input("Cantidad a ingresar", min_value=0.0, step=1.0, value=1.0)
            unidad = st.text_input("Unidad", value=str(row.get("unidad", "")))
            caducidad = st.text_input("Caducidad", value="" if pd.isna(row.get("caducidad")) else str(row.get("caducidad", "")))
        with form_col3:
            ubicacion = st.text_input("Ubicacion", value=str(row.get("ubicacion", "")))
            categoria = st.selectbox("Categoria", options=["REACTIVO", "MATERIAL", "OTRO"], index=0 if str(row.get("categoria", "")).upper() == "REACTIVO" else 1 if str(row.get("categoria", "")).upper() == "MATERIAL" else 2)
            fecha = st.date_input("Fecha", value=pd.Timestamp.today().date())
            responsable = st.text_input("Responsable", value="")
            temperatura = st.text_input("Temperatura (C)", value="")
        observaciones = st.text_area("Observaciones", value="Entrada agregada desde Corregir negativos.", height=80)
        submitted = st.form_submit_button("Guardar entrada faltante", use_container_width=True)
        if submitted:
            errors = []
            if cantidad <= 0:
                errors.append("La cantidad debe ser mayor a cero.")
            if errors:
                for error in errors:
                    st.error(error)
            else:
                repository.save_movement(
                    {
                        "inventory_scope": inventory_scope,
                        "movement_type": "entrada",
                        "id_registro": "",
                        "codigo": technical_code(catalogo, descripcion),
                        "descripcion": required_db_text(descripcion, "SIN DESCRIPCION"),
                        "catalogo": catalogo.strip(),
                        "marca": marca.strip(),
                        "lote": lote.strip(),
                        "cantidad": cantidad,
                        "unidad": unidad.strip(),
                        "caducidad": caducidad.strip(),
                        "ubicacion": ubicacion.strip(),
                        "categoria": categoria.strip(),
                        "fecha": parse_single_datetime(fecha).strftime("%Y-%m-%d"),
                        "responsable": required_db_text(responsable, "NO ESPECIFICADO"),
                        "temperatura": temperatura.strip(),
                        "observaciones": observaciones.strip(),
                        "verificado_por": "",
                    }
                )
                st.success("Entrada faltante guardada.")
                st.rerun()


def render_conflict_flag_form(row: pd.Series, inventory_scope: str) -> None:
    st.markdown("#### Marcar conflicto de homologacion")
    conflicts_df = load_conflict_flags()
    current_conflicts = conflicts_df.loc[
        (conflicts_df["inventory_scope"] == inventory_scope) & (conflicts_df["codigo_reportado"] == row["codigo"])
    ].copy()
    if not current_conflicts.empty:
        st.caption("Conflictos ya registrados para este codigo")
        st.dataframe(current_conflicts.sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)

    with st.form(f"homologation_conflict_{inventory_scope}_{row['codigo']}"):
        codigo_sugerido = st.text_input("Codigo sugerido", value="")
        motivo = st.selectbox(
            "Motivo",
            options=[
                "Codigo duplicado",
                "Codigo distinto para el mismo producto",
                "Catalogo inconsistente",
                "Marca o descripcion no homologada",
                "Otro",
            ],
        )
        detalle = st.text_area("Detalle", height=100)
        submitted = st.form_submit_button("Guardar conflicto", use_container_width=True)
        if submitted:
            save_conflict_flag(
                {
                    "created_at": pd.Timestamp.now().isoformat(),
                    "inventory_scope": inventory_scope,
                    "codigo_reportado": row.get("codigo", ""),
                    "codigo_sugerido": codigo_sugerido.strip(),
                    "descripcion": row.get("descripcion", ""),
                    "marca": row.get("marca", ""),
                    "motivo": motivo,
                    "detalle": detalle.strip(),
                }
            )
            st.success("Conflicto de homologacion guardado.")
            st.rerun()


def render_movement_form(
    movement_type: str,
    catalog_df: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    title = "Registrar entrada" if movement_type == "entrada" else "Registrar salida"
    st.subheader(title)
    st.caption("Este movimiento se guarda en la app y se suma al inventario del scope activo.")

    reset_state_key = f"movement_form_reset_{inventory_scope}_{movement_type}"
    if reset_state_key not in st.session_state:
        st.session_state[reset_state_key] = 0
    reset_nonce = st.session_state[reset_state_key]

    quick_catalog = st.text_input(
        "Teclea catalogo para autollenar",
        key=f"quick_catalog_{inventory_scope}_{movement_type}_{reset_nonce}",
        help="Si el catalogo ya existe, la app rellena descripcion, marca, categoria, unidad y ubicacion.",
    )
    quick_defaults, quick_match_count = prefill_values_from_catalog(quick_catalog, catalog_df)
    if quick_catalog.strip():
        if quick_match_count == 1:
            st.success("Catalogo encontrado. Datos autollenados.")
        elif quick_match_count > 1:
            st.info("Hay varias coincidencias para ese catalogo. Se uso la primera; revisa los datos antes de guardar.")
        else:
            st.warning("No encontre ese catalogo. Puedes capturarlo como nuevo insumo.")

    if movement_type == "salida":
        search_catalog = st.text_input(
            "Buscar por catalogo",
            key=f"search_catalog_{inventory_scope}_{movement_type}_{reset_nonce}",
            help="Busca por catalogo, descripcion o marca.",
        )
        filtered_catalog = catalog_df.copy()
        if search_catalog.strip():
            pattern = search_catalog.strip().lower()
            filtered_catalog = filtered_catalog.loc[
                filtered_catalog[["catalogo", "descripcion", "marca"]]
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
        key=f"selector_{inventory_scope}_{movement_type}_{reset_nonce}",
    )
    defaults = quick_defaults if quick_catalog.strip() and quick_match_count > 0 else prefill_values(selected_label, catalog_df)
    if quick_catalog.strip() and quick_match_count == 0:
        defaults["catalogo"] = quick_catalog.strip()

    default_signature = normalize_match_key(str(defaults.get("catalogo", "")) + str(defaults.get("descripcion", "")))
    with st.form(f"form_{inventory_scope}_{movement_type}_{reset_nonce}_{default_signature}", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            catalogo = st.text_input("Catalogo", value=str(defaults["catalogo"]))
            descripcion = st.text_input("Descripcion", value=str(defaults["descripcion"]))
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
            if cantidad <= 0:
                errors.append("La cantidad debe ser mayor a cero.")

            if errors:
                for error in errors:
                    st.error(error)
            else:
                try:
                    repository.save_movement(
                        {
                            "inventory_scope": inventory_scope,
                            "movement_type": movement_type,
                            "id_registro": "",
                            "codigo": technical_code(catalogo, descripcion),
                            "descripcion": required_db_text(descripcion, "SIN DESCRIPCION"),
                            "catalogo": catalogo.strip(),
                            "marca": marca.strip(),
                            "lote": lote.strip(),
                            "cantidad": cantidad,
                            "unidad": unidad.strip(),
                            "caducidad": caducidad.strip(),
                            "ubicacion": ubicacion.strip(),
                            "categoria": categoria.strip(),
                            "fecha": parse_single_datetime(fecha).strftime("%Y-%m-%d"),
                            "responsable": required_db_text(responsable, "NO ESPECIFICADO"),
                            "temperatura": temperatura.strip(),
                            "observaciones": observaciones.strip(),
                            "verificado_por": verificado_por.strip(),
                        }
                    )
                except Exception as exc:
                    st.error(str(exc))
                    st.info("El movimiento no se confirma como guardado hasta que Supabase lo acepte.")
                else:
                    st.success("Movimiento guardado correctamente.")
                    st.session_state[reset_state_key] = reset_nonce + 1
                    st.rerun()


def physical_counts_excel_bytes(counts_df: pd.DataFrame) -> bytes:
    output = BytesIO()
    export_df = counts_df.copy()
    if not export_df.empty:
        export_df["conteos_empatan"] = export_df["conteos_empatan"].map(lambda value: "SI" if bool(value) else "NO")
        export_df["ajuste_aplicado"] = export_df["ajuste_aplicado"].map(lambda value: "SI" if bool(value) else "NO")
        export_df = export_df[order_columns(export_df, PHYSICAL_COUNT_DISPLAY_COLUMNS)]
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name="Conteos fisicos", index=False)
    return output.getvalue()


def render_physical_counts_tab(
    general_inventory_df: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    st.subheader("Conteos fisicos")
    st.caption(
        "Registra un conteo y una verificacion. Solo si ambos numeros empatan, la app ajusta la existencia actual del catalogo."
    )

    option_source = general_inventory_df.copy()
    if option_source.empty:
        st.info("No hay catalogo disponible para conteo en este inventario.")
        return

    search = st.text_input(
        "Buscar catalogo para conteo",
        key=f"physical_count_search_{inventory_scope}",
        help="Busca por catalogo, descripcion, marca, lote o ubicacion.",
    )
    if search.strip():
        pattern = search.strip().lower()
        filtered_options = option_source.loc[
            option_source.astype(str)
            .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
            .any(axis=1)
        ].copy()
    else:
        filtered_options = option_source.loc[option_source["existencia"].fillna(0) > 0].copy()
        if filtered_options.empty:
            filtered_options = option_source.copy()

    if filtered_options.empty:
        st.warning("No encontre catalogos con ese criterio.")
        return

    count_options = build_catalog_options(filtered_options)
    selected_label = st.selectbox(
        "Selecciona el insumo contado",
        options=count_options,
        index=1 if len(count_options) > 1 else 0,
        key=f"physical_count_selector_{inventory_scope}_{normalize_match_key(search)}",
    )
    if selected_label == "Nuevo insumo":
        st.info("Para conteo fisico selecciona un insumo ya existente del inventario.")
        return

    selected_code = selected_label.split(" - ", 1)[0]
    selected_rows = filter_by_item_key(general_inventory_df, selected_code)
    if selected_rows.empty:
        st.error("No encontre el insumo seleccionado en el inventario actual.")
        return

    row = selected_rows.iloc[0]
    existencia_anterior = safe_float(row.get("existencia", 0))
    st.metric("Existencia actual antes del conteo", f"{existencia_anterior:,.0f}")

    with st.expander("Ficha del insumo", expanded=True):
        card_cols = st.columns(3)
        with card_cols[0]:
            st.markdown(f"**Catalogo:** {row.get('catalogo', '')}")
            st.markdown(f"**Descripcion:** {row.get('descripcion', '')}")
            st.markdown(f"**Marca:** {row.get('marca', '')}")
        with card_cols[1]:
            st.markdown(f"**Lote:** {row.get('lote', '')}")
            st.markdown(f"**Unidad:** {row.get('unidad', '')}")
            st.markdown(f"**Categoria:** {row.get('categoria', '')}")
        with card_cols[2]:
            st.markdown(f"**Ubicacion:** {row.get('ubicacion', '')}")
            st.markdown(f"**Caducidad:** {row.get('caducidad', '')}")

    with st.form(f"physical_count_form_{inventory_scope}_{selected_code}"):
        col1, col2, col3 = st.columns(3)
        with col1:
            fecha_conteo = st.date_input("Fecha de conteo", value=pd.Timestamp.today().date())
            contador = st.text_input("Nombre de quien cuenta")
        with col2:
            conteo_fisico = st.number_input("Primer conteo", min_value=0.0, step=1.0, value=existencia_anterior)
            verificador = st.text_input("Nombre de quien verifica")
        with col3:
            verificacion_fisica = st.number_input("Conteo de verificacion", min_value=0.0, step=1.0, value=existencia_anterior)
            observaciones = st.text_area("Observaciones", height=120)

        submitted = st.form_submit_button("Guardar conteo fisico", use_container_width=True)
        if submitted:
            errors = []
            if not contador.strip():
                errors.append("Indica el nombre de quien cuenta.")
            if not verificador.strip():
                errors.append("Indica el nombre de quien verifica.")
            if contador.strip() and verificador.strip() and normalize_text_key(contador) == normalize_text_key(verificador):
                errors.append("La verificacion debe registrarla una persona distinta a quien cuenta.")
            if errors:
                for error in errors:
                    st.error(error)
                return

            conteos_empatan = float(conteo_fisico) == float(verificacion_fisica)
            diferencia = float(conteo_fisico) - existencia_anterior if conteos_empatan else None
            count_uid = str(uuid4())
            movement_uid = str(uuid4()) if conteos_empatan and diferencia and diferencia != 0 else ""
            fecha_text = parse_single_datetime(fecha_conteo).strftime("%Y-%m-%d")
            base_payload = {
                "count_uid": count_uid,
                "inventory_scope": inventory_scope,
                "codigo": technical_code(row.get("catalogo", ""), row.get("descripcion", "")),
                "descripcion": required_db_text(row.get("descripcion", ""), "SIN DESCRIPCION"),
                "catalogo": str(row.get("catalogo", "") or "").strip(),
                "marca": str(row.get("marca", "") or "").strip(),
                "lote": str(row.get("lote", "") or "").strip(),
                "unidad": str(row.get("unidad", "") or "").strip(),
                "ubicacion": str(row.get("ubicacion", "") or "").strip(),
                "categoria": str(row.get("categoria", "") or "").strip(),
                "existencia_anterior": existencia_anterior,
                "conteo_fisico": float(conteo_fisico),
                "verificacion_fisica": float(verificacion_fisica),
                "conteos_empatan": conteos_empatan,
                "diferencia": diferencia,
                "ajuste_aplicado": False,
                "movement_uid": "",
                "fecha_conteo": fecha_text,
                "contador": contador.strip(),
                "verificador": verificador.strip(),
                "observaciones": observaciones.strip(),
            }

            try:
                repository.save_physical_count(base_payload)
            except Exception as exc:
                st.error(str(exc))
                st.info("El conteo no se confirma como guardado hasta que Supabase lo acepte.")
                return

            if movement_uid:
                try:
                    repository.save_movement(
                        {
                            "movement_uid": movement_uid,
                            "inventory_scope": inventory_scope,
                            "movement_type": "entrada" if diferencia > 0 else "salida",
                            "id_registro": f"CONTEO-{count_uid[:8]}",
                            "codigo": base_payload["codigo"],
                            "descripcion": base_payload["descripcion"],
                            "catalogo": base_payload["catalogo"],
                            "marca": base_payload["marca"],
                            "lote": base_payload["lote"],
                            "cantidad": abs(float(diferencia)),
                            "unidad": base_payload["unidad"],
                            "caducidad": str(row.get("caducidad", "") or "").strip(),
                            "ubicacion": base_payload["ubicacion"],
                            "categoria": base_payload["categoria"],
                            "fecha": fecha_text,
                            "responsable": required_db_text(contador, "NO ESPECIFICADO"),
                            "temperatura": "",
                            "observaciones": (
                                "Ajuste automatico por conteo fisico. "
                                f"Conteo: {conteo_fisico}; verificacion: {verificacion_fisica}. "
                                f"{observaciones.strip()}"
                            ).strip(),
                            "verificado_por": verificador.strip(),
                        }
                    )
                except Exception as exc:
                    st.error(str(exc))
                    st.info("El conteo quedo guardado, pero la existencia no se ajusto. Puedes revisar el historial antes de repetir.")
                    return

                base_payload["movement_uid"] = movement_uid
                base_payload["ajuste_aplicado"] = True
                try:
                    repository.upsert_physical_counts(pd.DataFrame([base_payload]))
                except Exception as exc:
                    st.warning(f"La existencia se ajusto, pero no pude marcar el conteo como aplicado. Detalle: {exc}")
                    return

            if not conteos_empatan:
                st.warning("Conteo guardado como no coincidente. No se actualizo la existencia.")
            elif movement_uid:
                st.success("Conteo guardado y existencia ajustada correctamente.")
            else:
                st.success("Conteo guardado. No hizo falta ajustar existencia.")
            st.rerun()

    counts_df = repository.load_physical_counts()
    scope_counts = counts_df.loc[counts_df["inventory_scope"].isin(get_scope_filter_values(inventory_scope))].copy()
    st.markdown("#### Historial de conteos")
    if scope_counts.empty:
        st.info("Aun no hay conteos fisicos guardados para este inventario.")
        return

    scope_counts = sort_by_existing_columns(scope_counts, ["fecha_conteo", "captured_at"], ascending=False)
    display_df = scope_counts[order_columns(scope_counts, PHYSICAL_COUNT_DISPLAY_COLUMNS)].copy()
    st.download_button(
        "Descargar Excel de conteos fisicos",
        data=physical_counts_excel_bytes(scope_counts),
        file_name=f"conteos_fisicos_{inventory_scope}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.dataframe(
        hide_display_columns(display_df),
        use_container_width=True,
        hide_index=True,
    )


def build_regularization_as_movements(regularizations_df: pd.DataFrame) -> pd.DataFrame:
    if regularizations_df.empty:
        return pd.DataFrame(columns=MOVEMENT_COLUMNS)
    df = regularizations_df.copy()
    payload = pd.DataFrame(
        {
            "movement_uid": df["regularization_uid"],
            "inventory_scope": df["inventory_scope"],
            "movement_type": "entrada",
            "id_registro": "REG-" + df["regularization_uid"].astype(str).str[:8],
            "codigo": df["codigo"],
            "descripcion": df["descripcion"],
            "catalogo": df["catalogo"],
            "marca": df["marca"],
            "lote": df["lote"],
            "cantidad": pd.to_numeric(df["cantidad"], errors="coerce").fillna(0),
            "unidad": df["unidad"],
            "caducidad": df["caducidad"],
            "ubicacion": df["ubicacion"],
            "categoria": df["categoria"],
            "fecha": df["fecha_corte"],
            "responsable": df["validado_por"],
            "temperatura": "",
            "observaciones": "Regularizacion inicial: " + df["tipo_regularizacion"].fillna("").astype(str),
            "verificado_por": df["validado_por"],
            "is_voided": False,
            "voided_at": None,
            "voided_by": None,
            "void_reason": None,
            "captured_at": df["captured_at"],
        }
    )
    return payload[MOVEMENT_COLUMNS]


def render_regularization_form(catalog_df: pd.DataFrame, repository, inventory_scope: str) -> None:
    st.subheader("Regularizacion inicial")
    st.caption("Usa este formulario solo para material fisico sin remision o para ajuste de conteo inicial. No sustituye una entrada normal.")

    selected_label = st.selectbox(
        "Selecciona un insumo",
        options=build_catalog_options(catalog_df),
        key=f"selector_{inventory_scope}_regularizacion",
    )
    defaults = prefill_values(selected_label, catalog_df)

    with st.form(f"form_{inventory_scope}_regularizacion", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            catalogo = st.text_input("Catalogo", value=str(defaults["catalogo"]))
            descripcion = st.text_input("Descripcion", value=str(defaults["descripcion"]))
            marca = st.text_input("Marca", value=str(defaults["marca"]))
            tipo_regularizacion = st.selectbox(
                "Tipo de regularizacion",
                options=["sin_remision", "donacion", "material_heredado", "ajuste_conteo_inicial"],
            )
        with col2:
            lote = st.text_input("Lote", value=str(defaults["lote"]))
            cantidad = st.number_input("Cantidad validada", min_value=0.0, step=1.0, value=1.0)
            unidad = st.text_input("Unidad", value=str(defaults["unidad"]))
            caducidad = st.text_input(
                "Caducidad",
                value="" if pd.isna(defaults["caducidad"]) else str(defaults["caducidad"]),
            )
            ubicacion = st.text_input("Ubicacion", value=str(defaults["ubicacion"]))
        with col3:
            category_options = ["REACTIVO", "MATERIAL", "OTRO"]
            default_category = str(defaults["categoria"]).upper()
            if default_category not in category_options:
                default_category = "OTRO"
            categoria = st.selectbox("Categoria", options=category_options, index=category_options.index(default_category))
            soporte_disponible = st.selectbox("Soporte disponible", options=["no", "parcial", "si"], index=0)
            fecha_corte = st.date_input("Fecha de corte", value=pd.Timestamp.today().date(), key=f"fecha_corte_{inventory_scope}")
            fecha_validacion = st.date_input("Fecha de validacion", value=pd.Timestamp.today().date(), key=f"fecha_validacion_{inventory_scope}")
            validado_por = st.text_input("Validado por")

        folio_origen = st.text_input("Folio o referencia origen (opcional)")
        comentario_regularizacion = st.text_area(
            "Comentario de regularizacion",
            height=120,
            placeholder="Ejemplo: material existente en fisico sin remision localizada.",
        )

        submitted = st.form_submit_button("Guardar regularizacion", use_container_width=True)
        if submitted:
            errors = []
            if not descripcion.strip():
                errors.append("La descripcion es obligatoria.")
            if cantidad <= 0:
                errors.append("La cantidad debe ser mayor a cero.")
            if not validado_por.strip():
                errors.append("La persona que valida es obligatoria.")
            if not comentario_regularizacion.strip():
                errors.append("El comentario de regularizacion es obligatorio.")
            if errors:
                for error in errors:
                    st.error(error)
            else:
                repository.save_regularization(
                    {
                        "inventory_scope": inventory_scope,
                        "tipo_regularizacion": tipo_regularizacion,
                        "fecha_corte": parse_single_datetime(fecha_corte).strftime("%Y-%m-%d"),
                        "fecha_validacion": parse_single_datetime(fecha_validacion).strftime("%Y-%m-%d"),
                        "codigo": technical_code(catalogo, descripcion),
                        "descripcion": descripcion.strip(),
                        "catalogo": catalogo.strip(),
                        "marca": marca.strip(),
                        "lote": lote.strip(),
                        "cantidad": cantidad,
                        "unidad": unidad.strip(),
                        "caducidad": caducidad.strip(),
                        "ubicacion": ubicacion.strip(),
                        "categoria": categoria.strip(),
                        "soporte_disponible": soporte_disponible,
                        "folio_origen": folio_origen.strip(),
                        "comentario_regularizacion": comentario_regularizacion.strip(),
                        "validado_por": validado_por.strip(),
                    }
                )
                st.success("Regularizacion guardada correctamente.")
                st.rerun()


def render_regularization_table(regularizations_df: pd.DataFrame, inventory_scope: str) -> None:
    st.subheader("Regularizaciones iniciales")
    st.caption("Estas regularizaciones se guardan por separado de entradas y salidas normales. Solo se deben aplicar al inventario oficial cuando autoricen el corte.")
    if regularizations_df.empty:
        st.info("No hay regularizaciones capturadas.")
        return
    filtered = regularizations_df.loc[regularizations_df["inventory_scope"].isin(get_scope_filter_values(inventory_scope))].copy()
    if filtered.empty:
        st.info("No hay regularizaciones para este scope.")
        return
    st.dataframe(
        hide_display_columns(filtered[order_columns(filtered, REGULARIZATION_DISPLAY_COLUMNS)]),
        use_container_width=True,
        hide_index=True,
    )


def render_catalog_editor(repository, inventory_scope: str, app_movements: pd.DataFrame) -> None:
    st.subheader("Editar catalogo")
    reset_state_key = f"catalog_editor_reset_{inventory_scope}"
    if reset_state_key not in st.session_state:
        st.session_state[reset_state_key] = 0
    reset_nonce = st.session_state[reset_state_key]
    st.caption(
        "Usa esta pestaña para corregir nombres ambiguos de materiales/reactivos. "
        "Si hay base oficial, actualiza la semilla; si no hay semilla, actualiza los movimientos capturados."
    )

    target_scope = st.selectbox(
        "Base a editar",
        options=[inventory_scope],
        format_func=lambda value: INVENTORY_SCOPES.get(value, value),
        key=f"catalog_editor_scope_{inventory_scope}_{reset_nonce}",
    )

    seed_df = repository.load_seed_entries(target_scope)
    editing_movements = seed_df.empty
    if editing_movements:
        source_df = filter_app_scope_rows(app_movements, target_scope)
        if source_df.empty:
            st.info("Todavia no hay base oficial ni movimientos capturados para editar.")
            return
        source_df = source_df.copy()
        source_df["row_id"] = source_df["movement_uid"]
        st.info("Frontera aun no tiene base oficial. Se editaran los movimientos capturados.")
    else:
        source_df = seed_df.copy()
        source_df = source_df.reset_index(drop=True)
        source_df["row_id"] = source_df.index

    editable_columns = ["descripcion", "catalogo", "marca", "categoria", "unidad", "ubicacion"]
    display_columns = [
        "row_id",
        "catalogo",
        "descripcion",
        "marca",
        "categoria",
        "unidad",
        "ubicacion",
        "cantidad",
        "lote",
        "caducidad",
        "source_label",
    ]
    search = st.text_input(
        "Buscar por catalogo, descripcion, marca o ubicacion",
        key=f"catalog_editor_search_{inventory_scope}_{target_scope}_{reset_nonce}",
    )
    filtered = source_df.copy()
    if search.strip():
        pattern = search.strip().lower()
        filtered = filtered.loc[
            filtered.astype(str)
            .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
            .any(axis=1)
        ].copy()

    st.caption(f"Editando {len(filtered)} de {len(source_df)} registros de `{target_scope}`.")
    edited = st.data_editor(
        filtered[order_columns(filtered, display_columns)],
        use_container_width=True,
        hide_index=True,
        disabled=[column for column in display_columns if column not in editable_columns],
        key=f"catalog_editor_{inventory_scope}_{target_scope}_{reset_nonce}",
    )

    if st.button("Guardar cambios de catalogo", key=f"save_catalog_editor_{inventory_scope}_{target_scope}_{reset_nonce}", use_container_width=True):
        updated_source = source_df.copy()
        edited = edited.copy()
        for column in editable_columns:
            if column not in edited.columns:
                continue
            values_by_row = edited.set_index("row_id")[column].to_dict()
            updated_source[column] = updated_source["row_id"].map(values_by_row).combine_first(updated_source[column])

        if editing_movements:
            updated_movements = updated_source.drop(columns=["row_id"])
            updated_movements["codigo"] = updated_movements.apply(
                lambda row: technical_code(row.get("catalogo", ""), row.get("descripcion", "")),
                axis=1,
            )
            try:
                repository.upsert_movements(updated_movements[MOVEMENT_COLUMNS])
            except Exception as exc:
                st.error(str(exc))
                return
        else:
            updated_seed = updated_source.drop(columns=["row_id"])
            updated_seed["codigo"] = updated_seed.apply(
                lambda row: technical_code(row.get("catalogo", ""), row.get("descripcion", "")),
                axis=1,
            )
            try:
                repository.replace_seed_entries(
                    target_scope,
                    updated_seed,
                    source_label=f"catalogo_editado_{target_scope}",
                )
            except Exception as exc:
                st.error(f"No se pudo guardar el catalogo en Supabase. Detalle: {exc}")
                return
        st.success("Catalogo actualizado.")
        st.session_state[reset_state_key] = reset_nonce + 1
        st.rerun()


def render_editable_captured_rows(
    selected_code: str,
    inventory_scope: str,
    app_movements: pd.DataFrame,
    repository,
) -> None:
    scope_rows = filter_app_scope_rows(app_movements, inventory_scope, selected_code)
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
        if "fecha" in editor_source.columns:
            editor_source["fecha"] = parse_mixed_datetime_series(editor_source["fecha"]).dt.date
        edited = st.data_editor(
            editor_source,
            hide_index=True,
            use_container_width=True,
            column_config={
                "fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
            },
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
            updated["codigo"] = updated.apply(
                lambda row: technical_code(row.get("catalogo", ""), row.get("descripcion", "")),
                axis=1,
            )
            updated["fecha"] = parse_mixed_datetime_series(updated["fecha"]).dt.strftime("%Y-%m-%d")
            updated["cantidad"] = pd.to_numeric(updated["cantidad"], errors="coerce").fillna(0)
            try:
                repository.upsert_movements(complete_movement_columns(updated, subset))
            except Exception as exc:
                st.error(str(exc))
                st.info("Los cambios no se confirman hasta que Supabase los acepte.")
            else:
                st.success(f"Se actualizaron las {movement_type}s capturadas.")
                st.rerun()


def render_capture_admin(app_movements: pd.DataFrame, repository, inventory_scope: str) -> None:
    st.subheader("Anular capturas")
    st.caption("Anula capturas equivocadas sin borrarlas de la auditoria. Las capturas anuladas ya no suman ni restan inventario.")

    source = filter_all_app_scope_rows(app_movements, inventory_scope)
    if source.empty:
        st.info("No hay capturas registradas para este inventario.")
        return

    source = source.copy()
    source["is_voided"] = source["is_voided"].fillna(False).astype(bool)
    show_voided = st.checkbox("Mostrar capturas anuladas", value=False, key=f"show_voided_movements_{inventory_scope}")
    visible = source.copy() if show_voided else source.loc[~source["is_voided"]].copy()

    search = st.text_input(
        "Buscar captura por catalogo, descripcion, marca, lote, responsable u observaciones",
        key=f"admin_capture_search_{inventory_scope}",
    )
    if search.strip():
        pattern = search.strip().lower()
        visible = visible.loc[
            visible.astype(str)
            .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
            .any(axis=1)
        ]

    visible = visible.sort_values("captured_at", ascending=False, na_position="last")
    display_columns = [column for column in MOVEMENT_ADMIN_COLUMNS + ["is_voided", "voided_by", "void_reason"] if column in visible.columns]
    st.dataframe(
        hide_display_columns(visible[order_columns(visible, display_columns)]),
        use_container_width=True,
        hide_index=True,
    )

    active = visible.loc[~visible["is_voided"]].copy()
    if active.empty:
        st.info("No hay capturas activas en esta vista para anular.")
        return

    options = []
    labels_by_uid = {}
    for _, row in active.iterrows():
        label = (
            f"{row.get('movement_type', '')} | {row.get('catalogo', '') or row.get('codigo', '')} | "
            f"{row.get('descripcion', '')} | {row.get('cantidad', '')} {row.get('unidad', '')} | "
            f"{row.get('fecha', '')}"
        )
        uid = str(row.get("movement_uid", ""))
        labels_by_uid[label] = uid
        options.append(label)

    with st.form(f"void_movement_form_{inventory_scope}"):
        selected_label = st.selectbox("Captura a anular", options=options)
        voided_by = st.text_input("Quien autoriza/anula", value="")
        void_reason = st.text_area("Motivo de anulacion", height=100)
        confirm = st.checkbox("Confirmo que esta captura no debe contar en el inventario")
        submitted = st.form_submit_button("Anular captura seleccionada", use_container_width=True)

        if submitted:
            if not voided_by.strip():
                st.error("Indica quien autoriza o realiza la anulacion.")
                return
            if not void_reason.strip():
                st.error("El motivo de anulacion es obligatorio.")
                return
            if not confirm:
                st.error("Marca la confirmacion antes de anular.")
                return

            uid = labels_by_uid[selected_label]
            updated = source.loc[source["movement_uid"].astype(str) == uid].copy()
            if updated.empty:
                st.error("No encontre la captura seleccionada.")
                return
            updated["is_voided"] = True
            updated["voided_at"] = pd.Timestamp.now().isoformat()
            updated["voided_by"] = voided_by.strip()
            updated["void_reason"] = void_reason.strip()
            try:
                repository.upsert_movements(updated[MOVEMENT_COLUMNS])
            except Exception as exc:
                st.error(str(exc))
                st.info("La anulacion no se confirma hasta que Supabase la acepte.")
            else:
                st.success("Captura anulada correctamente.")
                st.rerun()


def render_catalog_search(
    general_inventory_df: pd.DataFrame,
    app_movements: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    st.subheader("Buscador y edicion")
    st.caption(
        "Busca por catalogo, descripcion o marca. Desde aqui puedes localizar el activo y editar movimientos capturados para corregir negativos."
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

    options = [f"{get_item_key(row)} - {row['descripcion']}" for _, row in matches.head(50).iterrows()]
    selected = st.selectbox("Selecciona un activo", options=options, key=f"selected_asset_{inventory_scope}")
    selected_code = selected.split(" - ", 1)[0]
    row = filter_by_item_key(matches, selected_code).iloc[0]
    links = build_product_search_links(row)

    card_left, card_right = st.columns([2, 1])
    with card_left:
        st.markdown("### Ficha del activo")
        st.markdown(f"**Catalogo:** {row['catalogo']}")
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


def render_negative_correction_tab(
    general_inventory_df: pd.DataFrame,
    source_entry_df: pd.DataFrame,
    source_exit_df: pd.DataFrame,
    app_movements: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    st.subheader("Corregir negativos")
    diagnostics_df = build_negative_diagnostics(general_inventory_df, source_entry_df, source_exit_df)
    if diagnostics_df.empty:
        st.success("No hay claves negativas para corregir.")
        return

    st.caption("Busca por catalogo o descripcion y revisa entradas, salidas y movimientos capturados antes de corregir.")
    search = st.text_input("Buscar por catalogo", key=f"negative_fix_search_{inventory_scope}")
    filtered_negatives = diagnostics_df.copy()
    if search.strip():
        pattern = search.strip().lower()
        filtered_negatives = filtered_negatives.loc[
            filtered_negatives.astype(str)
            .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
            .any(axis=1)
        ].copy()
    if filtered_negatives.empty:
        st.warning("No encontre negativos con ese criterio.")
        return

    options = [
        f"{get_item_key(row)} - {row['descripcion']} ({float(row['existencia']):,.0f})"
        for _, row in filtered_negatives.sort_values("existencia").head(200).iterrows()
    ]
    selected = st.selectbox("Selecciona una clave negativa", options=options, key=f"negative_fix_code_{inventory_scope}")
    selected_code = selected.split(" - ", 1)[0]
    row = filter_by_item_key(filtered_negatives, selected_code).iloc[0]

    render_negative_item_card(row)

    source_entries = apply_canonical_display(filter_by_item_key(source_entry_df, selected_code))
    source_exits = apply_canonical_display(filter_by_item_key(source_exit_df, selected_code))
    related_variants = build_related_variant_rows(selected_code, general_inventory_df, source_entry_df, source_exit_df)
    app_rows = filter_app_scope_rows(app_movements, inventory_scope, selected_code)

    source_entries = sort_by_existing_columns(source_entries, ["fecha"], ascending=False)
    source_exits = sort_by_existing_columns(source_exits, ["fecha"], ascending=False)
    app_rows = sort_by_existing_columns(app_rows, ["fecha"], ascending=False)

    tab_related, tab_entries, tab_exits, tab_app, tab_actions = st.tabs(
        ["Variantes relacionadas", "Entradas fuente", "Salidas fuente", "Movimientos capturados en app", "Acciones"]
    )

    with tab_related:
        st.caption("Aqui se agrupan registros que podrian corresponder al mismo producto por catalogo parecido o misma descripcion/marca.")
        if related_variants.empty:
            st.info("No encontre variantes relacionadas para esta clave.")
        else:
            render_full_table(
                "Variantes relacionadas",
                related_variants,
                f"search_negative_related_{inventory_scope}_{selected_code}",
            )

    with tab_entries:
        if source_entries.empty:
            st.info("No hay entradas fuente para este catalogo.")
        else:
            render_full_table(
                "Entradas fuente",
                source_entries[
                    order_columns(
                        source_entries,
                        [
                            "id_registro",
                            "catalogo",
                            "catalogo_original",
                            "descripcion",
                            "descripcion_original",
                            "cantidad",
                            "unidad",
                            "fecha",
                            "responsable",
                            "marca",
                            "lote",
                            "caducidad",
                            "ubicacion",
                            "categoria",
                        ],
                    )
                ],
                f"search_negative_entries_{inventory_scope}_{selected_code}",
            )

    with tab_exits:
        if source_exits.empty:
            st.info("No hay salidas fuente para este catalogo.")
        else:
            render_full_table(
                "Salidas fuente",
                source_exits[
                    order_columns(
                        source_exits,
                        [
                            "id_registro",
                            "catalogo",
                            "catalogo_original",
                            "descripcion",
                            "descripcion_original",
                            "cantidad",
                            "unidad",
                            "fecha",
                            "responsable",
                            "marca",
                            "lote",
                            "caducidad",
                            "ubicacion",
                            "categoria",
                        ],
                    )
                ],
                f"search_negative_exits_{inventory_scope}_{selected_code}",
            )

    with tab_app:
        if app_rows.empty:
            st.info("No hay movimientos capturados en app para este catalogo.")
        else:
            render_full_table(
                "Movimientos capturados en app",
                app_rows[
                    order_columns(
                        app_rows,
                        ["movement_type", "id_registro", "catalogo", "descripcion", "marca", "lote", "cantidad", "unidad", "caducidad", "ubicacion", "categoria", "fecha", "responsable", "temperatura", "observaciones", "verificado_por", "inventory_scope"],
                    )
                ],
                f"search_negative_app_{inventory_scope}_{selected_code}",
            )

    with tab_actions:
        action_tab1, action_tab2, action_tab3 = st.tabs(
            ["Agregar entrada faltante", "Corregir salida capturada", "Marcar conflicto de homologacion"]
        )
        with action_tab1:
            render_add_missing_entry_form(row, repository, inventory_scope)
        with action_tab2:
            render_editable_captured_rows(selected_code, inventory_scope, app_movements, repository)
        with action_tab3:
            render_conflict_flag_form(row, inventory_scope)


def load_inventory_bundle(
    inventory_scope: str,
    recovery_workbook_source,
    indicators_workbook_source,
    materials_workbook_source,
    lit_workbook_source,
    repository,
    prefer_seed: bool = True,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    if prefer_seed:
        seed_df = repository.load_seed_entries_many(get_scope_filter_values(inventory_scope))
        if not seed_df.empty:
            return load_seed_inventory_frames(seed_df), pd.DataFrame(), pd.DataFrame()

    if inventory_scope == "lit":
        if lit_workbook_source is None:
            raise RuntimeError("No hay base oficial sembrada y tampoco existe el Excel oficial de LIT 01/07/2026.")
        return load_lit_official_inventory_frames(lit_workbook_source), pd.DataFrame(), pd.DataFrame()

    if inventory_scope == "frontera":
        return {"entradas": pd.DataFrame(), "salidas": pd.DataFrame(), "catalogo": pd.DataFrame()}, pd.DataFrame(), pd.DataFrame()

    raise RuntimeError(f"Inventario no soportado: {inventory_scope}")


def explain_load_error(exc: Exception, inventory_scope: str) -> None:
    st.error(f"No pude cargar el inventario `{INVENTORY_SCOPES[inventory_scope]}`: {exc}")
    if inventory_scope == "lit":
        st.info("Verifica que exista el Excel oficial de LIT 01/07/2026 o que la base oficial ya este sembrada en Supabase.")
    else:
        st.info("Frontera aun no tiene base inicial; empieza capturando entradas cuando sea necesario.")


def resolve_workbook_source(local_path: str, uploaded_file=None):
    if uploaded_file is not None:
        return BytesIO(uploaded_file.getvalue())
    path = Path(local_path)
    if path.exists():
        return path
    return None


def main() -> None:
    configure_users_backend()
    init_state()
    if not st.session_state["autenticado"]:
        render_auth_screen()
        return

    st.title("Inventario General INER")
    st.caption("Inventarios operativos: LIT y Frontera.")
    render_user_sidebar()
    render_user_admin_sidebar()

    repository = get_repository()

    inventory_scope = st.sidebar.radio(
        "Inventario activo",
        options=list(INVENTORY_SCOPES.keys()),
        index=list(INVENTORY_SCOPES.keys()).index(DEFAULT_SCOPE),
        format_func=lambda key: INVENTORY_SCOPES[key],
    )

    seed_available = not repository.load_seed_entries_many(get_scope_filter_values(inventory_scope)).empty
    app_movements = repository.load_movements()
    has_captured_movements = not filter_app_scope_rows(app_movements, inventory_scope).empty
    if seed_available:
        st.sidebar.success("Base oficial cargada.")
    elif has_captured_movements:
        st.sidebar.success("Movimientos capturados cargados.")
    else:
        st.sidebar.warning("No hay base oficial sembrada; se usaran Excel como respaldo.")

    materials_workbook_path = str(MATERIALS_WORKBOOK_PATH)
    lit_workbook_path = str(LIT_OFFICIAL_WORKBOOK_PATH)
    materials_upload = None
    lit_upload = None
    use_excel_fallback = False
    with st.sidebar.expander("Reconstruir desde Excel", expanded=not seed_available):
        use_excel_fallback = st.checkbox(
            "Usar Excel temporalmente en lugar de la base oficial",
            value=not seed_available,
            help="Activalo solo para revisar o reconstruir la base oficial.",
        )
        if inventory_scope == "lit":
            lit_workbook_path = st.text_input(
                "Excel oficial LIT",
                value=lit_workbook_path,
            )
            lit_upload = st.file_uploader(
                "Subir Excel oficial LIT",
                type=["xlsx", "xlsm", "xls"],
                key="lit_upload",
            )
        else:
            materials_workbook_path = st.text_input(
                "Excel Frontera/Federal",
                value=materials_workbook_path,
            )
            materials_upload = st.file_uploader(
                "Subir Excel Frontera/Federal",
                type=["xlsx", "xlsm", "xls"],
                key="materials_upload",
            )

    st.sidebar.markdown("**Fuente configurada**")
    if inventory_scope == "lit":
        st.sidebar.caption("LIT usa la base oficial si ya esta sembrada. Los Excel quedan como respaldo para reconstruirla.")
    else:
        st.sidebar.caption("Frontera usa la base oficial si ya esta sembrada. El Excel local queda como respaldo.")
    recovery_workbook_source = None
    indicators_workbook_source = None
    materials_workbook_source = None
    lit_workbook_source = None
    if inventory_scope == "lit":
        lit_workbook_source = resolve_workbook_source(lit_workbook_path, lit_upload)
    else:
        materials_workbook_source = resolve_workbook_source(materials_workbook_path, materials_upload)

    try:
        frames, registry_df, results_df = load_inventory_bundle(
            inventory_scope,
            recovery_workbook_source,
            indicators_workbook_source,
            materials_workbook_source,
            lit_workbook_source,
            repository,
            prefer_seed=not use_excel_fallback,
        )
    except Exception as exc:
        explain_load_error(exc, inventory_scope)
        return

    regularizations_df = repository.load_regularizations()
    apply_regularizations = st.sidebar.checkbox(
        "Aplicar regularizaciones al inventario actual",
        value=False,
        help="Activalo solo cuando autoricen formalmente el borrón y cuenta nueva.",
    )
    if apply_regularizations and not regularizations_df.empty:
        app_movements = pd.concat(
            [app_movements, build_regularization_as_movements(regularizations_df)],
            ignore_index=True,
        )

    scope_movements = filter_app_scope_rows(app_movements, inventory_scope)
    inventory_df, entry_df, exit_df, catalog_df = build_inventory_snapshot(
        frames["entradas"],
        frames["salidas"],
        scope_movements,
        catalog_df=frames.get("catalogo"),
    )

    general_inventory_df = inventory_df.copy()
    active_inventory_df = general_inventory_df.loc[general_inventory_df["existencia"].fillna(0) > 0].copy()

    st.markdown(f"### Inventario: {INVENTORY_SCOPES[inventory_scope]}")
    using_seed = seed_available and not use_excel_fallback
    if using_seed:
        st.caption("Fuente: base oficial sembrada. Los Excel ya no son necesarios para operar.")
    elif has_captured_movements:
        st.caption("Fuente: movimientos capturados. Este inventario todavia no tiene base oficial sembrada.")
    elif inventory_scope == "lit":
        st.caption("Fuente: base oficial LIT. Si no existe semilla, se reconstruye con JUL 26 + plantilla de recuperacion.")
    else:
        st.caption("Fuente: base oficial Frontera. Si no existe semilla, se reconstruye con el listado federal local.")

    total_items = len(active_inventory_df)
    total_stock = float(active_inventory_df["existencia"].fillna(0).sum()) if not active_inventory_df.empty else 0
    total_entries = float(entry_df["cantidad"].fillna(0).sum()) if not entry_df.empty else 0
    total_exits = float(exit_df["cantidad"].fillna(0).sum()) if not exit_df.empty else 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Claves activas", f"{total_items}")
    kpi2.metric("Existencia total", f"{total_stock:,.0f}")
    kpi3.metric("Entradas acumuladas", f"{total_entries:,.0f}")
    kpi4.metric("Salidas acumuladas", f"{total_exits:,.0f}")

    resumen_tab, recepcion_tab, salidas_tab, entrada_form_tab, salida_form_tab, conteos_fisicos_tab, buscador_tab, administrar_tab, regularizaciones_tab, negativos_tab, corregir_negativos_tab = st.tabs(
        [
            "Resumen general",
            "Entradas",
            "Salidas",
            "Registrar entrada",
            "Registrar salida",
            "Conteos fisicos",
            "Buscador y edicion",
            "Anular capturas",
            "Regularizaciones",
            "Negativos por revisar",
            "Corregir negativos",
        ]
    )

    with resumen_tab:
        st.subheader("Inventario general")
        if inventory_scope == "lit":
            st.info(
                f"Mostrando {len(active_inventory_df)} claves con existencia real. "
                f"Las claves de plantilla quedan disponibles para busqueda y captura, pero no suman existencia."
            )
        show_template_rows = st.checkbox(
            "Mostrar tambien claves de plantilla sin existencia",
            value=False,
            key=f"show_template_rows_{inventory_scope}",
        )
        categoria_filtro = st.multiselect(
            "Filtrar por categoria",
            options=sorted(general_inventory_df["categoria"].dropna().unique().tolist()),
            key=f"cat_filter_{inventory_scope}",
        )
        search = st.text_input(
            "Buscar por catalogo, descripcion, marca o ubicacion",
            key=f"search_inventario_{inventory_scope}",
        )
        filtered = general_inventory_df.copy() if show_template_rows else active_inventory_df.copy()
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
            hide_display_columns(filtered[order_columns(filtered, visible_columns)]),
            use_container_width=True,
            hide_index=True,
        )

    with negativos_tab:
        st.subheader("Negativos por revisar")
        negativos_df = build_negative_diagnostics(general_inventory_df, frames["entradas"], frames["salidas"])
        if negativos_df.empty:
            st.success("No hay claves con existencia negativa.")
        else:
            st.caption("Esta tabla ya intenta marcar cuando el negativo podria venir de variantes de escritura, entradas faltantes o mezcla de claves para la misma descripcion.")
            visible_columns = [column for column in NEGATIVE_DIAGNOSTIC_COLUMNS if column in negativos_df.columns]
            st.dataframe(
                hide_display_columns(negativos_df[order_columns(negativos_df, visible_columns)].sort_values("existencia")),
                use_container_width=True,
                hide_index=True,
            )

    with corregir_negativos_tab:
        render_negative_correction_tab(
            general_inventory_df=general_inventory_df,
            source_entry_df=frames["entradas"],
            source_exit_df=frames["salidas"],
            app_movements=app_movements,
            repository=repository,
            inventory_scope=inventory_scope,
        )

    with buscador_tab:
        render_catalog_search(general_inventory_df, app_movements, repository, inventory_scope)

    with administrar_tab:
        render_capture_admin(app_movements, repository, inventory_scope)

    with recepcion_tab:
        recepcion_df = sort_by_existing_columns(entry_df, ["fecha"], ascending=False).copy()
        visible_columns = [column for column in TABLE_COLUMNS + ["temperatura"] if column in recepcion_df.columns]
        render_full_table(
            "Entradas",
            rename_display_columns(
                recepcion_df[order_columns(recepcion_df, visible_columns)],
                {
                    "responsable": "Recibio",
                },
            ),
            f"search_recepcion_{inventory_scope}",
        )

    with salidas_tab:
        salidas_df = sort_by_existing_columns(exit_df, ["fecha"], ascending=False).copy()
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

    with conteos_fisicos_tab:
        render_physical_counts_tab(general_inventory_df, repository, inventory_scope)

    with regularizaciones_tab:
        regularization_view_tab, regularization_form_tab = st.tabs(["Ver regularizaciones", "Registrar regularizacion"])
        with regularization_view_tab:
            render_regularization_table(regularizations_df, inventory_scope)
        with regularization_form_tab:
            render_regularization_form(catalog_df, repository, inventory_scope)


if __name__ == "__main__":
    main()
