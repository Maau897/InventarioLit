from pathlib import Path

from inventory_app.config import MATERIALS_WORKBOOK_PATH
from inventory_app.excel_loader import load_material_inventory_frames
from inventory_app.repositories import get_repository


def main() -> None:
    repository = get_repository()
    workbook_path = Path(MATERIALS_WORKBOOK_PATH)
    if not workbook_path.exists():
        raise FileNotFoundError(f"No existe el archivo base: {workbook_path}")

    for scope in ["avimex", "federal"]:
        frames = load_material_inventory_frames(workbook_path, scope)
        seed_df = frames["entradas"][
            [
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
        ].copy()
        repository.replace_seed_entries(
            scope,
            seed_df,
            source_label="excel_seed",
        )
        print(f"{scope}: {len(seed_df)} registros sembrados en Supabase")


if __name__ == "__main__":
    main()
