from datetime import datetime, time
from pathlib import Path

import pandas as pd

from app.database import SessionLocal

from app.models import (
    BOM,
    Machine,
    MachineCalendar,
    MachineEvent,
    Material,
    Order,
    Product,
    Routing,
    SetupMatrix,
    Supplier,
    MaterialSupplier,
    MachineCapacity,
    StageCapacity,
    SetupExample,
)


# ============================================================
# HELPERS
# ============================================================

def to_datetime(value):

    if pd.isna(value):
        return None

    return pd.to_datetime(
        value
    ).to_pydatetime()


def to_date(value):

    if pd.isna(value):
        return None

    return pd.to_datetime(
        value
    ).date()


def to_time(value):

    if pd.isna(value):
        return None

    if isinstance(
        value,
        time,
    ):
        return value

    text = str(
        value
    ).strip()

    for fmt in (
        "%H:%M",
        "%H:%M:%S",
    ):

        try:

            return datetime.strptime(
                text,
                fmt
            ).time()

        except ValueError:
            continue

    raise ValueError(
        f"Cannot convert time value: {value}"
    )


def to_bool(value):

    if pd.isna(value):
        return False

    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        (int, float),
    ):
        return bool(value)

    text = str(
        value
    ).strip().lower()

    return text in {
        "true",
        "1",
        "yes",
        "y",
        "oui",
    }


def to_int(value):

    return int(
        float(value)
    )


def to_float(value):

    return float(value)


# ============================================================
# LOAD SUPPLIERS
# ============================================================

def load_suppliers(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            Supplier(
                supplier_id=str(
                    row["supplier_id"]
                ),
                supplier_name=str(
                    row["supplier_name"]
                ),
                material_scope=str(
                    row["material_scope"]
                ),
                lead_time_typical_days=to_float(
                    row["lead_time_typical_days"]
                ),
                otd_target_pct=to_float(
                    row["otd_target_pct"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD MATERIAL-SUPPLIER SOURCING
# ============================================================

def load_material_suppliers(df):
    rows=[]
    for row in df.to_dict("records"):
        rows.append(MaterialSupplier(
            material_id=str(row["material_id"]),
            supplier_id=str(row["supplier_id"]),
            priority_rank=to_int(row["priority_rank"]),
            is_preferred=to_bool(row["is_preferred"]),
            unit_cost_eur=to_float(row["unit_cost_eur"]),
            min_order_qty=to_float(row["min_order_qty"]),
            lot_size=to_float(row["lot_size"]),
            lead_time_days=to_int(row["lead_time_days"]),
            max_qty_per_day=to_float(row["max_qty_per_day"]),
            order_cost_eur=to_float(row["order_cost_eur"]),
            reliability_pct=to_float(row["reliability_pct"]),
            active=to_bool(row["active"]),
        ))
    return rows


# ============================================================
# LOAD MACHINES
# ============================================================

def load_machines(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            Machine(
                machine_id=str(
                    row["machine_id"]
                ),
                machine_name=str(
                    row["machine_name"]
                ),
                machine_type=str(
                    row["machine_type"]
                ),
                stage=str(
                    row["stage"]
                ),
                capacity_units_hour=to_float(
                    row["capacity_units_hour"]
                ),
                base_cycle_sec=to_float(
                    row["base_cycle_sec"]
                ),
                availability_pct=to_float(
                    row["availability_pct"]
                ),
                shift_pattern=str(
                    row["shift_pattern"]
                ),
                setup_skill=str(
                    row["setup_skill"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD PRODUCTS
# ============================================================

def load_products(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            Product(
                product_id=str(
                    row["product_id"]
                ),
                product_name=str(
                    row["product_name"]
                ),
                family=str(
                    row["family"]
                ),
                customer_mix=str(
                    row["customer_mix"]
                ),
                revision=str(
                    row["revision"]
                ),
                standard_batch_qty=to_int(
                    row["standard_batch_qty"]
                ),
                min_batch_qty=to_int(
                    row["min_batch_qty"]
                ),
                max_batch_qty=to_int(
                    row["max_batch_qty"]
                ),
                product_status=str(
                    row["product_status"]
                ),
                cycle_time_min_per_unit=to_float(
                    row[
                        "cycle_time_min_per_unit"
                    ]
                ),
                touch_time_min_per_unit=to_float(
                    row[
                        "touch_time_min_per_unit"
                    ]
                ),
            )
        )

    return rows


# ============================================================
# LOAD MATERIALS
# ============================================================

def load_materials(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            Material(
                material_id=str(
                    row["material_id"]
                ),
                material_name=str(
                    row["material_name"]
                ),
                material_type=str(
                    row["material_type"]
                ),
                uom=str(
                    row["uom"]
                ),
                on_hand_qty=to_float(
                    row["on_hand_qty"]
                ),
                safety_stock_qty=to_float(
                    row["safety_stock_qty"]
                ),
                lead_time_days=to_float(
                    row["lead_time_days"]
                ),
                supplier_id=str(
                    row["supplier_id"]
                ),
                lot_size=to_float(
                    row["lot_size"]
                ),
                horizon_requirement_qty=to_float(
                    row[
                        "horizon_requirement_qty"
                    ]
                ),
                avg_daily_requirement=to_float(
                    row[
                        "avg_daily_requirement"
                    ]
                ),
                coverage_days=to_float(
                    row["coverage_days"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD ROUTING
# ============================================================

def load_routing(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            Routing(
                product_id=str(
                    row["product_id"]
                ),
                operation_seq=to_int(
                    row["operation_seq"]
                ),
                operation_code=str(
                    row["operation_code"]
                ),
                operation_name=str(
                    row["operation_name"]
                ),
                machine_group=str(
                    row["machine_group"]
                ),
                compatible_machines=str(
                    row[
                        "compatible_machines"
                    ]
                ),
                operation_time_min_per_unit=to_float(
                    row[
                        "operation_time_min_per_unit"
                    ]
                ),
                setup_family=str(
                    row["setup_family"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD BOM
# ============================================================

def load_bom(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            BOM(
                product_id=str(
                    row["product_id"]
                ),
                material_id=str(
                    row["material_id"]
                ),
                qty_per_unit=to_float(
                    row["qty_per_unit"]
                ),
                scrap_factor_pct=to_float(
                    row["scrap_factor_pct"]
                ),
                consumption_operation_seq=to_int(
                    row.get("consumption_operation_seq", 10)
                ),
            )
        )

    return rows


# ============================================================
# LOAD ORDERS
# ============================================================

def load_orders(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            Order(
                order_id=str(
                    row["order_id"]
                ),
                customer=str(
                    row["customer"]
                ),
                product_id=str(
                    row["product_id"]
                ),
                order_qty=to_int(
                    row["order_qty"]
                ),
                order_date=to_datetime(
                    row["order_date"]
                ),
                requested_due_date=to_datetime(
                    row["requested_due_date"]
                ),
                priority_class=str(
                    row["priority_class"]
                ),
                priority_weight=to_int(
                    row["priority_weight"]
                ),
                order_status=str(
                    row["order_status"]
                ),
                is_urgent=to_bool(
                    row["is_urgent"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD MACHINE EVENTS
# ============================================================

def load_machine_events(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            MachineEvent(
                event_id=str(
                    row["event_id"]
                ),
                machine_id=str(
                    row["machine_id"]
                ),
                event_date=to_date(
                    row["event_date"]
                ),
                start_time=to_time(
                    row["start_time"]
                ),
                end_time=to_time(
                    row["end_time"]
                ),
                event_type=str(
                    row["event_type"]
                ),
                duration_h=to_float(
                    row["duration_h"]
                ),
                reason=str(
                    row["reason"]
                ),
                status=str(
                    row["status"]
                ),
                within_horizon=to_bool(
                    row["within_horizon"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD MACHINE CALENDAR
# ============================================================

def load_machine_calendar(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            MachineCalendar(
                machine_id=str(
                    row["machine_id"]
                ),
                calendar_date=to_date(
                    row["calendar_date"]
                ),
                is_workday=to_bool(
                    row["is_workday"]
                ),
                scheduled_hours=to_float(
                    row["scheduled_hours"]
                ),
                maintenance_hours=to_float(
                    row["maintenance_hours"]
                ),
                planned_available_hours=to_float(
                    row[
                        "planned_available_hours"
                    ]
                ),
                availability_factor=to_float(
                    row[
                        "availability_factor"
                    ]
                ),
            )
        )

    return rows


# ============================================================
# LOAD SETUP MATRIX
# ============================================================

def load_setup_matrix(df):

    rows = []

    for row in df.to_dict(
        "records"
    ):

        rows.append(
            SetupMatrix(
                machine_id=str(
                    row["machine_id"]
                ),
                from_product_id=str(
                    row["from_product_id"]
                ),
                to_product_id=str(
                    row["to_product_id"]
                ),
                setup_time_min=to_float(
                    row["setup_time_min"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD MACHINE CAPACITY
# ============================================================

def load_machine_capacity(df):
    rows = []

    for row in df.to_dict("records"):
        rows.append(
            MachineCapacity(
                machine_id=str(row["machine_id"]).strip(),
                stage=str(row["stage"]).strip(),
                scheduled_hours_h=to_float(row["scheduled_hours_h"]),
                planned_maintenance_h=to_float(row["planned_maintenance_h"]),
                planned_available_hours_h=to_float(
                    row["planned_available_hours_h"]
                ),
                nominal_capacity_units_h=to_float(
                    row["nominal_capacity_units_h"]
                ),
            )
        )

    return rows


# ============================================================
# LOAD STAGE CAPACITY
# ============================================================

def load_stage_capacity(df):
    rows = []

    for row in df.to_dict("records"):
        rows.append(
            StageCapacity(
                stage=str(row["stage"]).strip(),
                required_processing_hours_h=to_float(
                    row["required_processing_hours_h"]
                ),
                planned_available_hours_h=to_float(
                    row["planned_available_hours_h"]
                ),
                load_ratio_pct=to_float(row["load_ratio_pct"]),
                capacity_status=str(row["capacity_status"]).strip(),
            )
        )

    return rows


# ============================================================
# LOAD WIDE SETUP EXCEL INTO NORMALIZED TABLE
# ============================================================

def load_setup_example(df, setup_type):
    rows = []

    if "from_to" not in df.columns:
        raise ValueError(
            f"{setup_type}: required column 'from_to' is missing."
        )

    target_columns = [
        str(c).strip()
        for c in df.columns
        if str(c).strip() != "from_to"
    ]

    if not target_columns:
        raise ValueError(
            f"{setup_type}: no destination product columns found."
        )

    for row in df.to_dict("records"):
        from_product_id = str(row["from_to"]).strip()

        if not from_product_id or from_product_id.lower() == "nan":
            continue

        for to_product_id in target_columns:
            value = row.get(to_product_id)

            if pd.isna(value):
                continue

            rows.append(
                SetupExample(
                    setup_type=setup_type,
                    from_product_id=from_product_id,
                    to_product_id=to_product_id,
                    setup_time_min=to_float(value),
                )
            )

    return rows


def load_setup_asm_ex(df):
    return load_setup_example(df, "ASM")


def load_setup_crp_ex(df):
    return load_setup_example(df, "CRP")


# ============================================================
# LOADER REGISTRY
# ============================================================

DATASET_LOADERS = {

    "Suppliers":
        load_suppliers,

    "Material_Suppliers":
        load_material_suppliers,

    "Machine_Capacity":
        load_machine_capacity,

    "Stage_Capacity":
        load_stage_capacity,

    "Setup_ASM_Ex":
        load_setup_asm_ex,

    "Setup_CRP_Ex":
        load_setup_crp_ex,

    "Machines":
        load_machines,

    "Products":
        load_products,

    "Materials":
        load_materials,

    "Routing":
        load_routing,

    "BOM":
        load_bom,

    "Orders":
        load_orders,

    "Machine_Events":
        load_machine_events,

    "Machine_Calendar":
        load_machine_calendar,

    "Setup_Matrix":
        load_setup_matrix,
}


# ============================================================
# READ A SINGLE DATASET FILE
# ============================================================

def read_single_dataset(
    dataset_key: str,
    dataset_path: str,
):

    path = Path(
        dataset_path
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Dataset not found: "
            f"{path.resolve()}"
        )

    extension = (
        path.suffix.lower()
    )

    if extension == ".csv":

        return pd.read_csv(
            path
        )

    if extension in {
        ".xlsx",
        ".xls",
    }:

        excel = pd.ExcelFile(
            path
        )

        if not excel.sheet_names:

            raise ValueError(
                "Excel file contains no sheet."
            )

        return pd.read_excel(
            path,
            sheet_name=excel.sheet_names[0],
        )

    raise ValueError(
        f"Unsupported file extension: "
        f"{extension}"
    )


# ============================================================
# IMPORT ONE DATASET
# ============================================================

def import_single_dataset(
    dataset_key: str,
    dataset_path: str,
):

    if dataset_key not in DATASET_LOADERS:

        raise ValueError(
            f"Unsupported dataset key: "
            f"{dataset_key}"
        )

    print()
    print("=" * 70)
    print(
        f"IMPORT DATASET: {dataset_key}"
    )
    print("=" * 70)

    df = read_single_dataset(
        dataset_key,
        dataset_path,
    )

    print(
        f"Rows detected    : {len(df)}"
    )

    print(
        f"Columns detected : {len(df.columns)}"
    )

    loader = DATASET_LOADERS[
        dataset_key
    ]

    objects = loader(
        df
    )

    db = SessionLocal()

    try:

        imported = 0

        for obj in objects:

            db.merge(
                obj
            )

            imported += 1

        db.commit()

        print(
            f"Rows imported: {imported}"
        )

        print(
            f"{dataset_key} "
            "import completed successfully."
        )

        return {
            "dataset_key":
                dataset_key,

            "rows_imported":
                imported,
        }

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()


# ============================================================
# IMPORT COMPLETE WORKBOOK
#
# Used for:
# python -m app.import_data
#
# ============================================================

def import_all_data(
    dataset_path: str
):

    path = Path(
        dataset_path
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Dataset not found: "
            f"{path.resolve()}"
        )

    print()
    print("=" * 70)
    print("FULL EXCEL -> POSTGRESQL IMPORT")
    print("=" * 70)

    print(
        f"Dataset: {path.resolve()}"
    )

    excel = pd.ExcelFile(
        path
    )

    required_sheets = [
        "Machines",
        "Products",
        "Routing",
        "BOM",
        "Materials",
        "Orders",
        "Machine_Events",
        "Machine_Calendar",
        "Setup_Matrix",
        "Suppliers",
        "Material_Suppliers",
    ]

    missing = [
        sheet
        for sheet in required_sheets
        if sheet not in excel.sheet_names
    ]

    if missing:

        raise ValueError(
            "Missing required Excel sheets: "
            + ", ".join(missing)
        )

    # ========================================================
    # READ ALL SHEETS
    # ========================================================

    suppliers_df = pd.read_excel(
        path,
        sheet_name="Suppliers",
    )

    material_suppliers_df = pd.read_excel(
        path, sheet_name="Material_Suppliers",
    )

    machines_df = pd.read_excel(
        path,
        sheet_name="Machines",
    )

    products_df = pd.read_excel(
        path,
        sheet_name="Products",
    )

    materials_df = pd.read_excel(
        path,
        sheet_name="Materials",
    )

    routing_df = pd.read_excel(
        path,
        sheet_name="Routing",
    )

    bom_df = pd.read_excel(
        path,
        sheet_name="BOM",
    )

    orders_df = pd.read_excel(
        path,
        sheet_name="Orders",
    )

    events_df = pd.read_excel(
        path,
        sheet_name="Machine_Events",
    )

    calendar_df = pd.read_excel(
        path,
        sheet_name="Machine_Calendar",
    )

    setup_df = pd.read_excel(
        path,
        sheet_name="Setup_Matrix",
    )

    # ========================================================
    # CREATE OBJECTS
    # ========================================================

    suppliers = load_suppliers(
        suppliers_df
    )

    material_suppliers = load_material_suppliers(material_suppliers_df)

    machines = load_machines(
        machines_df
    )

    products = load_products(
        products_df
    )

    materials = load_materials(
        materials_df
    )

    routing = load_routing(
        routing_df
    )

    bom = load_bom(
        bom_df
    )

    orders = load_orders(
        orders_df
    )

    machine_events = load_machine_events(
        events_df
    )

    machine_calendar = load_machine_calendar(
        calendar_df
    )

    setup_matrix = load_setup_matrix(
        setup_df
    )

    # ========================================================
    # DATABASE
    # ========================================================

    db = SessionLocal()

    try:

        # ----------------------------------------------------
        # CLEAR ALL PROJECT DATA
        # ----------------------------------------------------
        # Optimization/scenario/event tables reference master data.
        # Delete dependents first so a clean Excel reload never fails
        # because an old scenario, breakdown or optimization result
        # still points to a product/machine/run.

        from app.models import (
            PlanningResult, OrderKPI, MachineKPI, MaterialKPI,
            OptimizationRun, ScenarioOrder, BreakdownEvent,
        )

        for model in (
            PlanningResult, OrderKPI, MachineKPI, MaterialKPI,
            ScenarioOrder, BreakdownEvent, OptimizationRun,
        ):
            db.query(model).delete(synchronize_session=False)

        db.flush()

        db.query(
            SetupMatrix
        ).delete(
            synchronize_session=False
        )

        db.query(
            BOM
        ).delete(
            synchronize_session=False
        )

        db.query(
            Routing
        ).delete(
            synchronize_session=False
        )

        db.query(
            Order
        ).delete(
            synchronize_session=False
        )

        db.query(
            MachineCalendar
        ).delete(
            synchronize_session=False
        )

        db.query(
            MachineEvent
        ).delete(
            synchronize_session=False
        )

        db.query(MaterialSupplier).delete(synchronize_session=False)

        db.query(
            Material
        ).delete(
            synchronize_session=False
        )

        db.query(
            Product
        ).delete(
            synchronize_session=False
        )

        db.query(
            Machine
        ).delete(
            synchronize_session=False
        )

        db.query(
            Supplier
        ).delete(
            synchronize_session=False
        )

        db.commit()

        # ----------------------------------------------------
        # INSERT IN FK ORDER
        # ----------------------------------------------------

        db.add_all(
            suppliers
        )

        db.flush()

        db.add_all(
            machines
        )

        db.flush()

        db.add_all(
            products
        )

        db.flush()

        db.add_all(
            materials
        )

        db.flush()

        db.add_all(material_suppliers)

        db.flush()

        db.add_all(
            routing
        )

        db.flush()

        db.add_all(
            bom
        )

        db.flush()

        db.add_all(
            orders
        )

        db.flush()

        db.add_all(
            machine_events
        )

        db.flush()

        db.add_all(
            machine_calendar
        )

        db.flush()

        db.add_all(
            setup_matrix
        )

        db.flush()

        db.commit()

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        summary = {
            "suppliers":
                len(suppliers),

            "machines":
                len(machines),

            "products":
                len(products),

            "materials":
                len(materials),

            "material_suppliers":
                len(material_suppliers),

            "routing":
                len(routing),

            "bom":
                len(bom),

            "orders":
                len(orders),

            "machine_events":
                len(machine_events),

            "machine_calendar":
                len(machine_calendar),

            "setup_matrix":
                len(setup_matrix),
        }

        print()
        print("=" * 70)
        print("FULL IMPORT COMPLETED")
        print("=" * 70)

        for key, value in summary.items():

            print(
                f"{key:<20}: {value}"
            )

        print()

        return summary

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()


# ============================================================
# STANDALONE EXECUTION
# ============================================================

if __name__ == "__main__":

    from app.config import DATASET_PATH

    import_all_data(
        DATASET_PATH
    )