import { useRef, useState } from "react";

import {
  CheckCircle2,
  Database,
  FileSpreadsheet,
  ShieldCheck,
  UploadCloud,
  XCircle,
} from "lucide-react";

import PageHeader from "../components/PageHeader";
import { importDataset } from "../api";


const fileDefinitions = [
  {
    key: "Orders",
    file: "Orders.xlsx",
  },
  {
    key: "Machines",
    file: "Machines.xlsx",
  },
  {
    key: "Materials",
    file: "Materials.xlsx",
  },
  {
    key: "BOM",
    file: "BOM.xlsx",
  },
  {
    key: "Routing",
    file: "Routing.xlsx",
  },
  {
    key: "Machine_Events",
    file: "Machine_Events.xlsx",
  },
  {
    key: "Machine_Calendar",
    file: "Machine_Calendar.xlsx",
  },
  {
    key: "Setup_Matrix",
    file: "Setup_Matrix.xlsx",
  },
  {
    key: "Suppliers",
    file: "Suppliers.xlsx",
  },
  {
    key: "Material_Suppliers",
    file: "matirialsuppl.xlsx",
  },
  {
    key: "Machine_Capacity",
    file: "Machine capacite.xlsx",
  },
  {
    key: "Stage_Capacity",
    file: "Stage_Capacity.xlsx",
  },
  {
    key: "Setup_ASM_Ex",
    file: "Setup_ASM_Ex.xlsx",
  },
  {
    key: "Setup_CRP_Ex",
    file: "Setup_CRP_Ex.xlsx",
  },
];


export default function DataManagement() {

  const [selected, setSelected] =
    useState({});

  const [validation, setValidation] =
    useState({});

  const [importStatus, setImportStatus] =
    useState({});

  const inputRefs =
    useRef({});


  // ============================================================
  // VALIDATE FILE LOCALLY
  // ============================================================

  function validateFile(file) {

    if (!file) {
      return {
        valid: false,
        message: "No file selected.",
      };
    }

    const extensionValid =
      /\.(xlsx|xls|csv)$/i.test(
        file.name
      );

    if (!extensionValid) {
      return {
        valid: false,
        message:
          "Invalid file type. Use .xlsx, .xls or .csv.",
      };
    }

    const sizeValid =
      file.size <=
      25 * 1024 * 1024;

    if (!sizeValid) {
      return {
        valid: false,
        message:
          "File too large. Maximum size is 25 MB.",
      };
    }

    return {
      valid: true,
      message: "File ready for validation.",
    };
  }


  // ============================================================
  // OPEN FILE PICKER
  // ============================================================

  function choose(definition) {

    const input =
      inputRefs.current[
        definition.key
      ];

    if (input) {
      input.click();
    }
  }


  // ============================================================
  // FILE SELECTED
  // ============================================================

  function onFile(
    definition,
    event
  ) {

    const file =
      event.target.files?.[0];

    if (!file) {
      return;
    }

    const result =
      validateFile(file);

    setSelected(
      (previous) => ({
        ...previous,
        [definition.key]: file,
      })
    );

    setValidation(
      (previous) => ({
        ...previous,
        [definition.key]: result,
      })
    );

    setImportStatus(
      (previous) => ({
        ...previous,
        [definition.key]: null,
      })
    );
  }


  // ============================================================
  // IMPORT TO POSTGRESQL
  // ============================================================

  async function handleUpload(
    definition
  ) {

    const file =
      selected[
        definition.key
      ];

    if (!file) {
      return;
    }

    const validationResult =
      validation[
        definition.key
      ];

    if (
      !validationResult?.valid
    ) {
      return;
    }

    setImportStatus(
      (previous) => ({
        ...previous,
        [definition.key]: {
          loading: true,
          success: false,
          message:
            "Uploading and validating...",
        },
      })
    );

    try {

      const result =
        await importDataset(
          file,
          definition.key
        );

      const success =
        result.status ===
        "IMPORTED";

      setImportStatus(
        (previous) => ({
          ...previous,
          [definition.key]: {
            loading: false,
            success,
            message:
              result.message ||
              (
                success
                  ? "Import completed successfully."
                  : "Import rejected."
              ),
            rows:
              result.rows_imported ??
              result.quality?.rows ??
              0,
            quality:
              result.quality ||
              null,
            errors:
              result.quality?.errors ||
              [],
          },
        })
      );

    } catch (error) {

      console.error(
        "DATA IMPORT ERROR:",
        error
      );

      const detail =
        error?.response?.data?.detail ||
        error?.message ||
        "Import failed.";

      setImportStatus(
        (previous) => ({
          ...previous,
          [definition.key]: {
            loading: false,
            success: false,
            message: detail,
            rows: 0,
            quality: null,
            errors: [],
          },
        })
      );
    }
  }


  // ============================================================
  // COUNTERS
  // ============================================================

  const selectedCount =
    Object.keys(selected).length;

  const validCount =
    Object.values(validation)
      .filter(
        (item) => item?.valid
      )
      .length;

  const importedCount =
    Object.values(importStatus)
      .filter(
        (item) =>
          item?.success === true
      )
      .length;


  // ============================================================
  // RENDER
  // ============================================================

  return (
    <>
      <PageHeader
        title="Data Management"
        description={
          "Import operational datasets, validate "
          +
          "their structure, and load them into PostgreSQL."
        }
      />

      {/* ======================================================
          INFO
      ====================================================== */}

      <div className="info-box">

        <Database size={16} />

        <span>
          PostgreSQL is the operational data source
          used by the optimizer. Each dataset can be
          imported independently.
        </span>

      </div>


      {/* ======================================================
          UPLOAD GRID
      ====================================================== */}

      <div className="upload-grid">

        {fileDefinitions.map(
          (definition) => {

            const file =
              selected[
                definition.key
              ];

            const validationResult =
              validation[
                definition.key
              ];

            const status =
              importStatus[
                definition.key
              ];

            const isValid =
              validationResult?.valid === true;

            return (

              <div
                className="upload-card"
                key={definition.key}
              >

                {/* ------------------------------------------------
                    ICON
                ------------------------------------------------ */}

                <div className="upload-icon">
                  <FileSpreadsheet
                    size={20}
                  />
                </div>


                {/* ------------------------------------------------
                    TITLE
                ------------------------------------------------ */}

                <strong>
                  {definition.file}
                </strong>


                {/* ------------------------------------------------
                    DESCRIPTION
                ------------------------------------------------ */}

                <p>
                  {file
                    ? `${file.name} • ${formatSize(
                        file.size
                      )}`
                    : "Select the operational file."
                  }
                </p>


                {/* ------------------------------------------------
                    REAL FILE INPUT
                ------------------------------------------------ */}

                <input
                  ref={(node) => {
                    inputRefs.current[
                      definition.key
                    ] = node;
                  }}
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  style={{
                    display: "none",
                  }}
                  onChange={(event) =>
                    onFile(
                      definition,
                      event
                    )
                  }
                />


                {/* ------------------------------------------------
                    CHOOSE FILE
                ------------------------------------------------ */}

                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() =>
                    choose(definition)
                  }
                >

                  <UploadCloud
                    size={16}
                  />

                  {file
                    ? "Change file"
                    : "Choose file"
                  }

                </button>


                {/* ------------------------------------------------
                    IMPORT BUTTON
                ------------------------------------------------ */}

                {file && isValid && (

                  <button
                    type="button"
                    className="button button-primary"
                    onClick={() =>
                      handleUpload(
                        definition
                      )
                    }
                    disabled={
                      status?.loading === true
                    }
                  >

                    <Database
                      size={16}
                    />

                    {status?.loading
                      ? "Importing..."
                      : "Import to PostgreSQL"
                    }

                  </button>

                )}


                {/* ------------------------------------------------
                    LOCAL VALIDATION
                ------------------------------------------------ */}

                <div
                  className={
                    "quality-line "
                    +
                    (
                      file &&
                      !isValid
                        ? "quality-error"
                        : ""
                    )
                  }
                >

                  {!file && (
                    <>
                      <ShieldCheck
                        size={15}
                      />

                      <span>
                        Waiting for file
                      </span>
                    </>
                  )}


                  {file && !isValid && (
                    <>
                      <XCircle
                        size={15}
                      />

                      <span>
                        {validationResult?.message ||
                          "Invalid file"}
                      </span>
                    </>
                  )}


                  {file && isValid && (
                    <>
                      <CheckCircle2
                        size={15}
                      />

                      <span>
                        Ready for server validation
                      </span>
                    </>
                  )}

                </div>


                {/* ------------------------------------------------
                    SERVER RESULT
                ------------------------------------------------ */}

                {status && (
                  <div
                    className={
                      status.success
                        ? "import-result success"
                        : "import-result error"
                    }
                  >

                    {status.success ? (
                      <CheckCircle2
                        size={15}
                      />
                    ) : (
                      <XCircle
                        size={15}
                      />
                    )}

                    <div>

                      <div>
                        {status.message}
                      </div>

                      {status.success && (
                        <small>
                          {status.rows} rows imported
                        </small>
                      )}

                      {!status.success &&
                        status.errors?.length > 0 && (
                          <small>
                            {status.errors
                              .slice(0, 2)
                              .map(
                                (error, index) => (
                                  <div
                                    key={index}
                                  >
                                    {typeof error === "string"
                                      ? error
                                      : JSON.stringify(
                                          error
                                        )}
                                  </div>
                                )
                              )}
                          </small>
                        )}

                    </div>

                  </div>
                )}

              </div>
            );
          }
        )}

      </div>


      {/* ======================================================
          QUALITY GATE
      ====================================================== */}

      <div className="panel">

        <div className="panel-header">

          <div>

            <h2>
              Data Quality Gate
            </h2>

            <p>
              Critical master data must be valid
              before production optimization.
            </p>

          </div>

          <span className="section-counter">

            {validCount}
            /
            {fileDefinitions.length}

            {" "}files valid

          </span>

        </div>


        <div className="quality-grid">

          <Quality
            label="Files selected"
            value={`${selectedCount}/${fileDefinitions.length}`}
          />

          <Quality
            label="Files valid"
            value={`${validCount}/${fileDefinitions.length}`}
          />

          <Quality
            label="Files imported"
            value={`${importedCount}/${fileDefinitions.length}`}
          />

          <Quality
            label="Source"
            value="PostgreSQL"
          />

        </div>


        <div className="data-issues">

          <div>

            <ShieldCheck
              size={16}
            />

            <span>
              Extension and file-size validation
              is performed locally.
            </span>

          </div>


          <div>

            <Database
              size={16}
            />

            <span>
              Server-side validation is performed
              before database import.
            </span>

          </div>


          <div>

            <CheckCircle2
              size={16}
            />

            <span>
              Each dataset is imported independently.
            </span>

          </div>

        </div>

      </div>

    </>
  );
}


// ============================================================
// QUALITY COMPONENT
// ============================================================

function Quality({
  label,
  value,
}) {

  return (

    <div className="quality-card">

      <div>

        <strong>
          {label}
        </strong>

        <span>
          Status
        </span>

      </div>

      <strong className="quality-value">
        {value}
      </strong>

    </div>
  );
}


// ============================================================
// FILE SIZE
// ============================================================

function formatSize(bytes) {

  if (!bytes) {
    return "0 KB";
  }

  if (
    bytes <
    1024 * 1024
  ) {

    return (
      `${(
        bytes / 1024
      ).toFixed(0)} KB`
    );
  }

  return (
    `${(
      bytes /
      (1024 * 1024)
    ).toFixed(1)} MB`
  );
}