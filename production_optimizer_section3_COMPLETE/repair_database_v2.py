from sqlalchemy import text, inspect

from app.database import engine, Base
import app.models  # important : charge tous les modèles


def repair_database():
    print("=" * 70)
    print("DATABASE V2 SCHEMA REPAIR")
    print("=" * 70)

    inspector = inspect(engine)

    # ---------------------------------------------------------
    # 1. Vérifier la table BOM
    # ---------------------------------------------------------

    tables = inspector.get_table_names()

    if "bom" not in tables:
        print("ERROR: table 'bom' does not exist.")
        print("Run reset_and_import.py instead.")
        return

    bom_columns = {
        column["name"]
        for column in inspector.get_columns("bom")
    }

    print("\nBOM columns:")
    for column in sorted(bom_columns):
        print(f"  - {column}")

    # ---------------------------------------------------------
    # 2. Ajouter consumption_operation_seq si absent
    # ---------------------------------------------------------

    if "consumption_operation_seq" not in bom_columns:

        print(
            "\nAdding column "
            "'bom.consumption_operation_seq'..."
        )

        with engine.begin() as conn:

            conn.execute(
                text(
                    """
                    ALTER TABLE bom
                    ADD COLUMN consumption_operation_seq
                    INTEGER NOT NULL DEFAULT 10
                    """
                )
            )

        print(
            "OK: consumption_operation_seq added."
        )

    else:

        print(
            "\nOK: consumption_operation_seq "
            "already exists."
        )

    # ---------------------------------------------------------
    # 3. Créer les éventuelles nouvelles tables
    # ---------------------------------------------------------

    print(
        "\nChecking SQLAlchemy V2 tables..."
    )

    Base.metadata.create_all(
        bind=engine
    )

    # ---------------------------------------------------------
    # 4. Vérification finale
    # ---------------------------------------------------------

    inspector = inspect(engine)

    final_columns = {
        column["name"]
        for column in inspector.get_columns("bom")
    }

    if "consumption_operation_seq" in final_columns:

        print(
            "\nSUCCESS"
        )

        print(
            "bom.consumption_operation_seq "
            "is now available."
        )

    else:

        print(
            "\nERROR: column was not created."
        )
        return

    print("\n" + "=" * 70)
    print("DATABASE REPAIR COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    repair_database()