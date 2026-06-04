import os
from dataclasses import dataclass
from uuid import uuid4

import pandas as pd

from inventory_app.config import LOCAL_DATA_DIR, LOCAL_MOVEMENTS_PATH

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


@dataclass
class LocalCsvRepository:
    path: str = str(LOCAL_MOVEMENTS_PATH)

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


class SupabaseRepository:
    def __init__(self) -> None:
        from supabase import create_client

        self.url = os.getenv("SUPABASE_URL", "")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
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
        self.client.table("inventory_movements").insert(payload).execute()
        self.local_backup.save_movement(payload)

    def upsert_movements(self, movements_df: pd.DataFrame) -> None:
        payload_df = _ensure_movement_columns(movements_df)
        records = payload_df.to_dict(orient="records")
        if records:
            self.client.table("inventory_movements").upsert(
                records,
                on_conflict="movement_uid",
            ).execute()
        self.local_backup.upsert_movements(payload_df)


def get_repository():
    supabase_ready = bool(
        os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    if supabase_ready:
        return SupabaseRepository()
    return LocalCsvRepository()
