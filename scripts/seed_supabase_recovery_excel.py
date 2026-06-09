from pathlib import Path

import pandas as pd

from inventory_app.config import RECOVERY_WORKBOOK_PATH
from inventory_app.excel_loader import build_inventory_snapshot, load_workbook_frames
from inventory_app.repositories import get_repository


def main() -> None:
    repository = get_repository()
    workbook_path = Path(RECOVERY_WORKBOOK_PATH)
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
        "recuperacion",
        seed_df,
        source_label="recovery_excel_seed",
    )
    print(f"recuperacion: {len(seed_df)} registros sembrados en Supabase")


if __name__ == "__main__":
    main()
