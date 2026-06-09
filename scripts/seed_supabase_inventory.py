from pathlib import Path
import sys
import argparse

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from inventory_app.config import MATERIALS_WORKBOOK_PATH
from inventory_app.excel_loader import load_material_inventory_frames
from inventory_app.repositories import get_repository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(MATERIALS_WORKBOOK_PATH))
    parser.add_argument("--general-scope", default="general")
    parser.add_argument("--federal-scope", default="federal")
    args = parser.parse_args()

    repository = get_repository()
    workbook_path = Path(args.path)
    if not workbook_path.exists():
        raise FileNotFoundError(f"No existe el archivo base: {workbook_path}")

    scope_map = {
        "avimex": args.general_scope,
        "federal": args.federal_scope,
    }

    for source_scope in ["avimex", "federal"]:
        target_scope = scope_map[source_scope]
        frames = load_material_inventory_frames(workbook_path, source_scope)
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
            target_scope,
            seed_df,
            source_label=f"{source_scope}_excel_seed",
        )
        print(f"{target_scope}: {len(seed_df)} registros sembrados en Supabase")


if __name__ == "__main__":
    main()
