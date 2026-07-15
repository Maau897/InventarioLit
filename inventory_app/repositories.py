import os
from dataclasses import dataclass
from uuid import uuid4

import pandas as pd

from inventory_app.config import (
    LOCAL_DATA_DIR,
    LOCAL_MOVEMENTS_PATH,
    LOCAL_REGULARIZATIONS_PATH,
    LOCAL_SEED_ENTRIES_PATH,
)

SEED_COLUMNS = [
    "inventory_scope",
    "codigo_local",
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
    "source_label",
    "loaded_at",
]

MOVEMENT_COLUMNS = [
    "movement_uid",
    "inventory_scope",
    "movement_type",
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
    "captured_at",
]

REGULARIZATION_COLUMNS = [
    "regularization_uid",
    "inventory_scope",
    "tipo_regularizacion",
    "fecha_corte",
    "fecha_validacion",
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
    "soporte_disponible",
    "folio_origen",
    "comentario_regularizacion",
    "validado_por",
    "captured_at",
]


def _get_config_value(secret_key: str, env_key: str, default: str = "") -> str:
    try:
        import streamlit as st

        return str(st.secrets.get(secret_key, os.getenv(env_key, default)))
    except Exception:
        return str(os.getenv(env_key, default))


def _ensure_movement_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in MOVEMENT_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df["movement_uid"] = df["movement_uid"].fillna("").astype(str).str.strip()
    missing_uid_mask = df["movement_uid"] == ""
    if missing_uid_mask.any():
        df.loc[missing_uid_mask, "movement_uid"] = [str(uuid4()) for _ in range(missing_uid_mask.sum())]
    df["inventory_scope"] = (
        df["inventory_scope"].fillna("recuperacion").astype(str).str.strip().replace("", "recuperacion")
    )
    return df[MOVEMENT_COLUMNS]


def _sanitize_records_df(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned = cleaned.replace({pd.NA: None})
    cleaned = cleaned.where(pd.notna(cleaned), None)
    return cleaned


def _remote_write_error(action: str, exc: Exception) -> RuntimeError:
    detail = str(exc).strip() or exc.__class__.__name__
    return RuntimeError(f"No se pudo {action} en Supabase. Detalle: {detail}")


def _ensure_regularization_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in REGULARIZATION_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df["regularization_uid"] = df["regularization_uid"].fillna("").astype(str).str.strip()
    missing_uid_mask = df["regularization_uid"] == ""
    if missing_uid_mask.any():
        df.loc[missing_uid_mask, "regularization_uid"] = [str(uuid4()) for _ in range(missing_uid_mask.sum())]
    df["inventory_scope"] = (
        df["inventory_scope"].fillna("general").astype(str).str.strip().replace("", "general")
    )
    return df[REGULARIZATION_COLUMNS]


@dataclass
class LocalCsvRepository:
    path: str = str(LOCAL_MOVEMENTS_PATH)
    regularizations_path: str = str(LOCAL_REGULARIZATIONS_PATH)
    seed_entries_path: str = str(LOCAL_SEED_ENTRIES_PATH)

    def load_movements(self) -> pd.DataFrame:
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not LOCAL_MOVEMENTS_PATH.exists():
            return pd.DataFrame(columns=MOVEMENT_COLUMNS)
        df = pd.read_csv(self.path)
        return _ensure_movement_columns(df)

    def save_movement(self, payload: dict[str, object]) -> None:
        df = self.load_movements()
        payload = payload.copy()
        payload["movement_uid"] = str(payload.get("movement_uid") or uuid4())
        payload["inventory_scope"] = str(payload.get("inventory_scope") or "recuperacion")
        payload["captured_at"] = payload.get("captured_at") or pd.Timestamp.now().isoformat()
        updated = pd.concat([df, pd.DataFrame([payload])], ignore_index=True)
        _ensure_movement_columns(updated).to_csv(self.path, index=False)

    def upsert_movements(self, movements_df: pd.DataFrame) -> None:
        existing = self.load_movements()
        incoming = _ensure_movement_columns(movements_df)
        merged = existing.set_index("movement_uid")
        incoming_indexed = incoming.set_index("movement_uid")
        merged.update(incoming_indexed)
        missing_rows = incoming_indexed.loc[~incoming_indexed.index.isin(merged.index)]
        if not missing_rows.empty:
            merged = pd.concat([merged, missing_rows], axis=0)
        merged.reset_index().to_csv(self.path, index=False)

    def load_seed_entries(self, inventory_scope: str) -> pd.DataFrame:
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not LOCAL_SEED_ENTRIES_PATH.exists():
            return pd.DataFrame(columns=SEED_COLUMNS)
        df = pd.read_csv(self.seed_entries_path)
        for column in SEED_COLUMNS:
            if column not in df.columns:
                df[column] = None
        df["inventory_scope"] = df["inventory_scope"].fillna("").astype(str).str.strip()
        return df.loc[df["inventory_scope"] == inventory_scope, SEED_COLUMNS].copy()

    def load_seed_entries_many(self, inventory_scopes: list[str]) -> pd.DataFrame:
        frames = [self.load_seed_entries(scope) for scope in inventory_scopes]
        frames = [df for df in frames if not df.empty]
        if not frames:
            return pd.DataFrame(columns=SEED_COLUMNS)
        return pd.concat(frames, ignore_index=True)

    def replace_seed_entries(
        self,
        inventory_scope: str,
        seed_df: pd.DataFrame,
        source_label: str = "",
    ) -> None:
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if LOCAL_SEED_ENTRIES_PATH.exists():
            existing = pd.read_csv(self.seed_entries_path)
            for column in SEED_COLUMNS:
                if column not in existing.columns:
                    existing[column] = None
            existing = existing.loc[existing["inventory_scope"].astype(str) != inventory_scope, SEED_COLUMNS].copy()
        else:
            existing = pd.DataFrame(columns=SEED_COLUMNS)

        incoming = seed_df.copy()
        for column in SEED_COLUMNS:
            if column not in incoming.columns:
                incoming[column] = None
        incoming["inventory_scope"] = inventory_scope
        incoming["source_label"] = source_label
        incoming["loaded_at"] = pd.Timestamp.now().isoformat()
        incoming = incoming[SEED_COLUMNS]
        updated = pd.concat([existing, incoming], ignore_index=True)
        updated.to_csv(self.seed_entries_path, index=False)

    def load_regularizations(self) -> pd.DataFrame:
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not LOCAL_REGULARIZATIONS_PATH.exists():
            return pd.DataFrame(columns=REGULARIZATION_COLUMNS)
        df = pd.read_csv(self.regularizations_path)
        return _ensure_regularization_columns(df)

    def save_regularization(self, payload: dict[str, object]) -> None:
        df = self.load_regularizations()
        payload = payload.copy()
        payload["regularization_uid"] = str(payload.get("regularization_uid") or uuid4())
        payload["inventory_scope"] = str(payload.get("inventory_scope") or "general")
        payload["captured_at"] = payload.get("captured_at") or pd.Timestamp.now().isoformat()
        updated = pd.concat([df, pd.DataFrame([payload])], ignore_index=True)
        _ensure_regularization_columns(updated).to_csv(self.regularizations_path, index=False)


class SupabaseRepository:
    def __init__(self) -> None:
        from supabase import create_client

        self.url = _get_config_value("supabase_url", "SUPABASE_URL", "")
        self.key = _get_config_value("supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.key:
            self.key = _get_config_value("supabase_key", "SUPABASE_KEY", "")
        self.client = create_client(self.url, self.key)
        self.local_backup = LocalCsvRepository()

    def load_movements(self) -> pd.DataFrame:
        response = self.client.table("inventory_movements").select("*").execute()
        data = response.data or []
        if not data:
            return self.local_backup.load_movements()
        df = pd.DataFrame(data)
        return _ensure_movement_columns(df)

    def save_movement(self, payload: dict[str, object]) -> None:
        payload = payload.copy()
        payload["movement_uid"] = str(payload.get("movement_uid") or uuid4())
        payload["inventory_scope"] = str(payload.get("inventory_scope") or "recuperacion")
        payload["captured_at"] = payload.get("captured_at") or pd.Timestamp.now().isoformat()
        clean_payload = _sanitize_records_df(_ensure_movement_columns(pd.DataFrame([payload]))).to_dict(orient="records")[0]
        try:
            self.client.table("inventory_movements").insert(clean_payload).execute()
        except Exception as exc:
            self.local_backup.save_movement(payload)
            raise _remote_write_error("guardar el movimiento", exc) from exc
        self.local_backup.save_movement(payload)

    def upsert_movements(self, movements_df: pd.DataFrame) -> None:
        payload_df = _ensure_movement_columns(movements_df)
        payload_df = _sanitize_records_df(payload_df)
        records = payload_df.to_dict(orient="records")
        if records:
            try:
                self.client.table("inventory_movements").upsert(
                    records,
                    on_conflict="movement_uid",
                ).execute()
            except Exception as exc:
                self.local_backup.upsert_movements(payload_df)
                raise _remote_write_error("actualizar movimientos", exc) from exc
        self.local_backup.upsert_movements(payload_df)

    def load_seed_entries(self, inventory_scope: str) -> pd.DataFrame:
        response = (
            self.client.table("inventory_seed_entries")
            .select("*")
            .eq("inventory_scope", inventory_scope)
            .execute()
        )
        data = response.data or []
        if not data:
            return pd.DataFrame(columns=SEED_COLUMNS)
        df = pd.DataFrame(data)
        for column in SEED_COLUMNS:
            if column not in df.columns:
                df[column] = None
        return df[SEED_COLUMNS]

    def load_seed_entries_many(self, inventory_scopes: list[str]) -> pd.DataFrame:
        if not inventory_scopes:
            return pd.DataFrame(columns=SEED_COLUMNS)
        response = (
            self.client.table("inventory_seed_entries")
            .select("*")
            .in_("inventory_scope", inventory_scopes)
            .execute()
        )
        data = response.data or []
        if not data:
            return pd.DataFrame(columns=SEED_COLUMNS)
        df = pd.DataFrame(data)
        for column in SEED_COLUMNS:
            if column not in df.columns:
                df[column] = None
        return df[SEED_COLUMNS]

    def replace_seed_entries(
        self,
        inventory_scope: str,
        seed_df: pd.DataFrame,
        source_label: str = "",
    ) -> None:
        delete_query = (
            self.client.table("inventory_seed_entries")
            .delete()
            .eq("inventory_scope", inventory_scope)
        )
        delete_query.execute()

        if seed_df.empty:
            return

        payload_df = seed_df.copy()
        for column in SEED_COLUMNS:
            if column not in payload_df.columns:
                payload_df[column] = None
        payload_df["inventory_scope"] = inventory_scope
        payload_df["source_label"] = source_label
        payload_df["loaded_at"] = pd.Timestamp.now().isoformat()
        payload_df = payload_df[SEED_COLUMNS]
        payload_df = _sanitize_records_df(payload_df)
        self.client.table("inventory_seed_entries").insert(
            payload_df.to_dict(orient="records")
        ).execute()

    def load_regularizations(self) -> pd.DataFrame:
        try:
            response = self.client.table("inventory_regularizations").select("*").execute()
            data = response.data or []
            if not data:
                return self.local_backup.load_regularizations()
            df = pd.DataFrame(data)
            return _ensure_regularization_columns(df)
        except Exception:
            return self.local_backup.load_regularizations()

    def save_regularization(self, payload: dict[str, object]) -> None:
        payload = payload.copy()
        payload["regularization_uid"] = str(payload.get("regularization_uid") or uuid4())
        payload["inventory_scope"] = str(payload.get("inventory_scope") or "general")
        payload["captured_at"] = payload.get("captured_at") or pd.Timestamp.now().isoformat()
        clean_payload = _sanitize_records_df(pd.DataFrame([payload]))[REGULARIZATION_COLUMNS].to_dict(orient="records")[0]
        try:
            self.client.table("inventory_regularizations").insert(clean_payload).execute()
        except Exception as exc:
            self.local_backup.save_regularization(payload)
            raise _remote_write_error("guardar la regularizacion", exc) from exc
        self.local_backup.save_regularization(payload)


def get_repository():
    supabase_ready = bool(
        _get_config_value("supabase_url", "SUPABASE_URL", "")
        and (
            _get_config_value("supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY", "")
            or _get_config_value("supabase_key", "SUPABASE_KEY", "")
        )
    )
    if supabase_ready:
        return SupabaseRepository()
    return LocalCsvRepository()
