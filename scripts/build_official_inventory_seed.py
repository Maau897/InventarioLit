from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from inventory_app.config import LIT_OFFICIAL_WORKBOOK_PATH
from inventory_app.excel_loader import (
    build_inventory_snapshot,
    load_lit_official_inventory_frames,
)
from inventory_app.repositories import LocalCsvRepository, get_repository


SEED_EXPORT_COLUMNS = [
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
]


def _snapshot_to_seed(frames: dict[str, pd.DataFrame], source_label: str) -> pd.DataFrame:
    inventory_df, _, _, _ = build_inventory_snapshot(
        frames["entradas"],
        frames["salidas"],
        pd.DataFrame(),
        catalog_df=frames.get("catalogo"),
    )
    seed_df = inventory_df.copy()
    seed_df["cantidad"] = seed_df["existencia"].fillna(0).clip(lower=0)
    seed_df["codigo"] = seed_df["catalogo"].fillna("").astype(str).str.strip()
    missing_code = seed_df["codigo"] == ""
    seed_df.loc[missing_code, "codigo"] = seed_df.loc[missing_code, "descripcion"].fillna("").astype(str).str.strip()
    seed_df["codigo"] = seed_df["codigo"].replace("", "SIN CATALOGO")
    seed_df["source_label"] = source_label
    seed_df = seed_df.sort_values(["categoria", "descripcion", "catalogo", "codigo"])
    return seed_df[SEED_EXPORT_COLUMNS + ["source_label"]].copy()


def build_lit_seed(lit_path: Path) -> pd.DataFrame:
    frames = load_lit_official_inventory_frames(lit_path)
    return _snapshot_to_seed(frames, "base_oficial_lit_01_07_2026")


def build_empty_frontera_seed() -> pd.DataFrame:
    return pd.DataFrame(columns=SEED_EXPORT_COLUMNS + ["source_label"])


def _print_summary(scope: str, seed_df: pd.DataFrame) -> None:
    active = seed_df.loc[pd.to_numeric(seed_df["cantidad"], errors="coerce").fillna(0) > 0].copy()
    print(f"{scope}: {len(active)} claves activas")
    print(f"{scope}: {float(active['cantidad'].sum()):,.0f} existencia total")
    print(f"{scope}: {len(seed_df) - len(active)} claves de plantilla/sin existencia")


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye y guarda la base oficial de inventario.")
    parser.add_argument("--lit", action="store_true", help="Construir base oficial LIT.")
    parser.add_argument("--frontera", action="store_true", help="Construir base oficial Frontera.")
    parser.add_argument("--all", action="store_true", help="Construir ambas bases.")
    parser.add_argument("--lit-path", default=str(LIT_OFFICIAL_WORKBOOK_PATH))
    parser.add_argument("--local-only", action="store_true", help="Guardar solo en data/inventory_seed_entries.csv.")
    args = parser.parse_args()

    build_lit = args.all or args.lit or (not args.lit and not args.frontera)
    build_frontera = args.all or args.frontera
    repository = LocalCsvRepository() if args.local_only else get_repository()

    if build_lit:
        lit_seed = build_lit_seed(Path(args.lit_path))
        repository.replace_seed_entries("lit", lit_seed, source_label="base_oficial_lit_01_07_2026")
        _print_summary("LIT", lit_seed)

    if build_frontera:
        frontera_seed = build_empty_frontera_seed()
        repository.replace_seed_entries("frontera", frontera_seed, source_label="frontera_pendiente")
        _print_summary("Frontera", frontera_seed)


if __name__ == "__main__":
    main()
