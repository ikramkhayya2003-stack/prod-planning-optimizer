from pathlib import Path

import pandas as pd


# ============================================================
# REQUIRED COLUMNS FOR EACH DATASET
# ============================================================

SINGLE_DATASET_COLUMNS = {

    "Suppliers": [
        "supplier_id",
        "supplier_name",
        "material_scope",
        "lead_time_typical_days",
        "otd_target_pct",
    ],

    "Material_Suppliers": [
        "material_id",
        "supplier_id",
        "priority_rank",
        "is_preferred",
        "unit_cost_eur",
        "min_order_qty",
        "lot_size",
        "lead_time_days",
        "max_qty_per_day",
        "order_cost_eur",
        "reliability_pct",
        "active",
    ],

    "Machine_Capacity": [
        "machine_id",
        "stage",
        "scheduled_hours_h",
        "planned_maintenance_h",
        "planned_available_hours_h",
        "nominal_capacity_units_h",
    ],

    "Stage_Capacity": [
        "stage",
        "required_processing_hours_h",
        "planned_available_hours_h",
        "load_ratio_pct",
        "capacity_status",
    ],

    "Setup_ASM_Ex": [
        "from_to",
    ],

    "Setup_CRP_Ex": [
        "from_to",
    ],

    "Machines": [
        "machine_id",
        "machine_name",
        "machine_type",
        "stage",
        "capacity_units_hour",
        "base_cycle_sec",
        "availability_pct",
        "shift_pattern",
        "setup_skill",
    ],

    "Products": [
        "product_id",
        "product_name",
        "family",
        "customer_mix",
        "revision",
        "standard_batch_qty",
        "min_batch_qty",
        "max_batch_qty",
        "product_status",
        "cycle_time_min_per_unit",
        "touch_time_min_per_unit",
    ],

    "Materials": [
        "material_id",
        "material_name",
        "material_type",
        "uom",
        "on_hand_qty",
        "safety_stock_qty",
        "lead_time_days",
        "supplier_id",
        "lot_size",
        "horizon_requirement_qty",
        "avg_daily_requirement",
        "coverage_days",
    ],

    "Routing": [
        "product_id",
        "operation_seq",
        "operation_code",
        "operation_name",
        "machine_group",
        "compatible_machines",
        "operation_time_min_per_unit",
        "setup_family",
    ],

    "BOM": [
        "product_id",
        "material_id",
        "qty_per_unit",
        "scrap_factor_pct",
    ],

    "Orders": [
        "order_id",
        "customer",
        "product_id",
        "order_qty",
        "order_date",
        "requested_due_date",
        "priority_class",
        "priority_weight",
        "order_status",
        "is_urgent",
    ],

    "Machine_Events": [
        "event_id",
        "machine_id",
        "event_date",
        "start_time",
        "end_time",
        "event_type",
        "duration_h",
        "reason",
        "status",
        "within_horizon",
    ],

    "Machine_Calendar": [
        "machine_id",
        "calendar_date",
        "is_workday",
        "scheduled_hours",
        "maintenance_hours",
        "planned_available_hours",
        "availability_factor",
    ],

    "Setup_Matrix": [
        "machine_id",
        "from_product_id",
        "to_product_id",
        "setup_time_min",
    ],
}


# ============================================================
# PRIMARY KEY COLUMN
# ============================================================

PRIMARY_KEY_COLUMNS = {

    "Suppliers": "supplier_id",

    "Machines": "machine_id",

    "Products": "product_id",

    "Materials": "material_id",

    "Orders": "order_id",

    "Machine_Events": "event_id",
}


# ============================================================
# READ FILE
# ============================================================

def _read_dataset_file(
    dataset_key: str,
    file_path: str,
):
    """
    Read a single uploaded dataset.

    Supported:
        .xlsx
        .xls
        .csv
    """

    path = Path(file_path)

    if not path.exists():

        raise FileNotFoundError(
            f"File not found: {path.resolve()}"
        )

    extension = (
        path.suffix.lower()
    )

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    if extension == ".csv":

        return pd.read_csv(
            path
        )

    # --------------------------------------------------------
    # EXCEL
    # --------------------------------------------------------

    if extension in {
        ".xlsx",
        ".xls",
    }:

        excel = pd.ExcelFile(
            path
        )

        if not excel.sheet_names:

            raise ValueError(
                "Excel file contains no worksheets."
            )

        # For individual files, the first worksheet
        # is considered the dataset.
        return pd.read_excel(
            path,
            sheet_name=excel.sheet_names[0],
        )

    raise ValueError(
        f"Unsupported file extension: "
        f"{extension}"
    )


# ============================================================
# CHECK REQUIRED COLUMNS
# ============================================================

def _check_required_columns(
    df,
    dataset_key,
    errors,
):
    """
    Verify that the uploaded dataset contains
    all columns required by the database model.
    """

    required_columns = (
        SINGLE_DATASET_COLUMNS[
            dataset_key
        ]
    )

    actual_columns = {
        str(column).strip()
        for column in df.columns
    }

    missing_columns = [
        column
        for column in required_columns
        if column not in actual_columns
    ]

    if missing_columns:

        errors.append(
            {
                "type": "MISSING_COLUMNS",
                "dataset": dataset_key,
                "columns": missing_columns,
                "message": (
                    "Required columns are missing."
                ),
            }
        )


# ============================================================
# CHECK DUPLICATES
# ============================================================

def _check_duplicates(
    df,
    dataset_key,
    warnings,
):
    """
    Detect duplicate primary identifiers.
    """

    primary_column = (
        PRIMARY_KEY_COLUMNS.get(
            dataset_key
        )
    )

    if (
        primary_column is None
        or primary_column not in df.columns
    ):
        return

    duplicate_count = int(
        df[primary_column]
        .astype(str)
        .duplicated()
        .sum()
    )

    if duplicate_count > 0:

        warnings.append(
            {
                "type": "DUPLICATE_PRIMARY_KEY",
                "dataset": dataset_key,
                "column": primary_column,
                "count": duplicate_count,
                "message": (
                    f"{duplicate_count} duplicate "
                    f"{primary_column} values found."
                ),
            }
        )


# ============================================================
# CHECK COMMON DATA QUALITY RULES
# ============================================================

def _check_business_rules(
    df,
    dataset_key,
    errors,
    warnings,
):
    """
    Apply lightweight business validation rules.
    """

    # --------------------------------------------------------
    # ORDERS
    # --------------------------------------------------------

    if dataset_key == "Orders":

        if "order_qty" in df.columns:

            numeric_qty = pd.to_numeric(
                df["order_qty"],
                errors="coerce",
            )

            invalid = int(
                (
                    numeric_qty.isna()
                    | (numeric_qty <= 0)
                ).sum()
            )

            if invalid > 0:

                errors.append(
                    {
                        "type": "INVALID_ORDER_QTY",
                        "count": invalid,
                        "message": (
                            "Orders contain invalid "
                            "quantities."
                        ),
                    }
                )

        if "requested_due_date" in df.columns:

            invalid_dates = int(
                pd.to_datetime(
                    df["requested_due_date"],
                    errors="coerce",
                ).isna().sum()
            )

            if invalid_dates > 0:

                errors.append(
                    {
                        "type": "INVALID_DUE_DATE",
                        "count": invalid_dates,
                        "message": (
                            "Orders contain invalid "
                            "requested due dates."
                        ),
                    }
                )

        if "priority_class" in df.columns:

            valid_priorities = {
                "A",
                "B",
                "C",
            }

            priorities = (
                df["priority_class"]
                .astype(str)
                .str.upper()
                .str.strip()
            )

            invalid = int(
                (~priorities.isin(
                    valid_priorities
                )).sum()
            )

            if invalid > 0:

                warnings.append(
                    {
                        "type": "INVALID_PRIORITY",
                        "count": invalid,
                        "message": (
                            "Some orders have a "
                            "priority outside A/B/C."
                        ),
                    }
                )

    # --------------------------------------------------------
    # MACHINES
    # --------------------------------------------------------

    if dataset_key == "Machines":

        if "availability_pct" in df.columns:

            availability = pd.to_numeric(
                df["availability_pct"],
                errors="coerce",
            )

            invalid = int(
                (
                    availability.isna()
                    | (availability < 0)
                    | (availability > 100)
                ).sum()
            )

            if invalid > 0:

                errors.append(
                    {
                        "type": "INVALID_AVAILABILITY",
                        "count": invalid,
                        "message": (
                            "Availability must be "
                            "between 0 and 100%."
                        ),
                    }
                )

    # --------------------------------------------------------
    # MATERIALS
    # --------------------------------------------------------

    if dataset_key == "Materials":

        if "on_hand_qty" in df.columns:

            stock = pd.to_numeric(
                df["on_hand_qty"],
                errors="coerce",
            )

            negative_stock = int(
                (
                    stock < 0
                ).sum()
            )

            if negative_stock > 0:

                warnings.append(
                    {
                        "type": "NEGATIVE_STOCK",
                        "count": negative_stock,
                        "message": (
                            "Negative on-hand stock "
                            "values detected."
                        ),
                    }
                )

        if "coverage_days" in df.columns:

            coverage = pd.to_numeric(
                df["coverage_days"],
                errors="coerce",
            )

            critical = int(
                (
                    coverage < 7
                ).sum()
            )

            if critical > 0:

                warnings.append(
                    {
                        "type": "LOW_COVERAGE",
                        "count": critical,
                        "message": (
                            f"{critical} materials have "
                            "less than 7 days of coverage."
                        ),
                    }
                )

    # --------------------------------------------------------
    # BOM
    # --------------------------------------------------------

    if dataset_key == "BOM":

        if "qty_per_unit" in df.columns:

            qty = pd.to_numeric(
                df["qty_per_unit"],
                errors="coerce",
            )

            invalid = int(
                (
                    qty.isna()
                    | (qty <= 0)
                ).sum()
            )

            if invalid > 0:

                errors.append(
                    {
                        "type": "INVALID_BOM_QTY",
                        "count": invalid,
                        "message": (
                            "BOM quantity per unit "
                            "must be greater than zero."
                        ),
                    }
                )

    # --------------------------------------------------------
    # ROUTING
    # --------------------------------------------------------

    if dataset_key == "Routing":

        if "operation_time_min_per_unit" in df.columns:

            operation_time = pd.to_numeric(
                df[
                    "operation_time_min_per_unit"
                ],
                errors="coerce",
            )

            invalid = int(
                (
                    operation_time.isna()
                    | (operation_time <= 0)
                ).sum()
            )

            if invalid > 0:

                errors.append(
                    {
                        "type": "INVALID_OPERATION_TIME",
                        "count": invalid,
                        "message": (
                            "Operation time must be "
                            "greater than zero."
                        ),
                    }
                )

    # --------------------------------------------------------
    # SETUP MATRIX
    # --------------------------------------------------------

    if dataset_key == "Setup_Matrix":

        if "setup_time_min" in df.columns:

            setup_time = pd.to_numeric(
                df["setup_time_min"],
                errors="coerce",
            )

            invalid = int(
                (
                    setup_time.isna()
                    | (setup_time < 0)
                ).sum()
            )

            if invalid > 0:

                errors.append(
                    {
                        "type": "INVALID_SETUP_TIME",
                        "count": invalid,
                        "message": (
                            "Setup time cannot be negative."
                        ),
                    }
                )


# ============================================================
# MAIN SINGLE DATASET VALIDATION
# ============================================================

def validate_single_dataset(
    dataset_key: str,
    file_path: str,
):
    """
    Validate one uploaded dataset.

    Important:
    This validates only the selected dataset.
    It does NOT require the other Excel files.
    """

    # --------------------------------------------------------
    # DATASET KEY
    # --------------------------------------------------------

    if dataset_key not in SINGLE_DATASET_COLUMNS:

        raise ValueError(
            f"Unsupported dataset key: "
            f"{dataset_key}"
        )

    # --------------------------------------------------------
    # READ
    # --------------------------------------------------------

    df = _read_dataset_file(
        dataset_key,
        file_path,
    )

    errors = []

    warnings = []

    # --------------------------------------------------------
    # EMPTY DATASET
    # --------------------------------------------------------

    if df.empty:

        errors.append(
            {
                "type": "EMPTY_DATASET",
                "dataset": dataset_key,
                "message": (
                    "The uploaded dataset is empty."
                ),
            }
        )

    # --------------------------------------------------------
    # COLUMNS
    # --------------------------------------------------------

    _check_required_columns(
        df,
        dataset_key,
        errors,
    )

    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    _check_duplicates(
        df,
        dataset_key,
        warnings,
    )

    # --------------------------------------------------------
    # BUSINESS RULES
    # --------------------------------------------------------

    _check_business_rules(
        df,
        dataset_key,
        errors,
        warnings,
    )

    # --------------------------------------------------------
    # QUALITY SCORE
    # --------------------------------------------------------

    quality_score = 100

    quality_score -= (
        len(errors) * 20
    )

    quality_score -= (
        len(warnings) * 5
    )

    quality_score = max(
        0,
        min(
            100,
            quality_score,
        ),
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {

        "valid":
            len(errors) == 0,

        "dataset_key":
            dataset_key,

        "filename":
            Path(file_path).name,

        "rows":
            int(len(df)),

        "columns":
            int(len(df.columns)),

        "quality_score":
            quality_score,

        "error_count":
            len(errors),

        "warning_count":
            len(warnings),

        "errors":
            errors,

        "warnings":
            warnings,

    }


# ============================================================
# FULL WORKBOOK VALIDATION
# ============================================================

REQUIRED_SHEETS = [
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
]


def validate_excel_file(
    file_path: str,
):
    """
    Validate a complete production workbook.

    This function is kept for compatibility with the
    full-workbook workflow.
    """

    path = Path(file_path)

    if not path.exists():

        raise FileNotFoundError(
            f"File not found: {path.resolve()}"
        )

    excel = pd.ExcelFile(
        path
    )

    errors = []

    warnings = []

    missing_sheets = [
        sheet
        for sheet in REQUIRED_SHEETS
        if sheet not in excel.sheet_names
    ]

    if missing_sheets:

        errors.append(
            {
                "type": "MISSING_SHEETS",
                "sheets": missing_sheets,
                "message": (
                    "Required sheets are missing."
                ),
            }
        )

        return {
            "valid": False,
            "filename": path.name,
            "quality_score": 0,
            "errors": errors,
            "warnings": warnings,
            "sheets": excel.sheet_names,
        }

    statistics = {}

    for dataset_key in REQUIRED_SHEETS:

        result = validate_single_dataset(
            dataset_key,
            str(path),
        )

        statistics[
            dataset_key
        ] = {
            "rows": result["rows"],
            "columns": result["columns"],
            "quality_score": result[
                "quality_score"
            ],
        }

        errors.extend(
            result["errors"]
        )

        warnings.extend(
            result["warnings"]
        )

    quality_score = max(
        0,
        100 -
        len(errors) * 10 -
        len(warnings) * 5,
    )

    return {

        "valid":
            len(errors) == 0,

        "filename":
            path.name,

        "quality_score":
            quality_score,

        "error_count":
            len(errors),

        "warning_count":
            len(warnings),

        "sheets":
            excel.sheet_names,

        "statistics":
            statistics,

        "errors":
            errors,

        "warnings":
            warnings,
    }