from pathlib import Path
import sys
import argparse

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from inventory_app.config import RECOVERY_WORKBOOK_PATH
from inventory_app.excel_loader import build_inventory_snapshot, load_workbook_frames
from inventory_app.repositories import get_repository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(RECOVERY_WORKBOOK_PATH))
    parser.add_argument("--scope", default="general")
    args = parser.parse_args()

    repository = get_repository()
    workbook_path = Path(args.path)
    if not workbook_path.exists():
        raise FileNotFoundError(f"No existe el archivo base: {workbook_path}")

    frames = load_workbook_frames(workbook_path)
    inventory_df, _, _, _ = build_inventory_snapshot(
        frames["entradas"],
        frames["salidas"],
        pd.DataFrame(),
        catalog_df=frames["catalogo"],
    )

    seed_df = inventory_df[
        [
            "codigo_local",
            "codigo",
            "descripcion",
            "catalogo",
            "marca",
            "lote",
            "existencia",
            "unidad",
            "caducidad",
            "ubicacion",
            "categoria",
        ]
    ].copy()
    seed_df = seed_df.rename(columns={"existencia": "cantidad"})
    repository.replace_seed_entries(
        args.scope,
        seed_df,
        source_label="recovery_excel_seed",
    )
    print(f"{args.scope}: {len(seed_df)} registros sembrados en Supabase")


if __name__ == "__main__":
    main()
