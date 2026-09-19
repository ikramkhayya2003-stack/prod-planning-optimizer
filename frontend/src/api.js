import axios from "axios";

// ============================================================
// API CONFIGURATION
// ============================================================

const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API_BASE_URL.replace(/\/$/, ""),
  timeout: 120000,
  headers: {
    Accept: "application/json",
  },
});

// Keep the original Axios error object so pages can still read
// error.response.data.detail when FastAPI returns a useful message.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API request failed", {
      method: error.config?.method?.toUpperCase(),
      url: error.config?.url,
      status: error.response?.status,
      data: error.response?.data,
      message: error.message,
    });
    return Promise.reject(error);
  },
);

// ============================================================
// OPTIMIZATION
// ============================================================

export async function startOptimization(payload) {
  const response = await api.post("/optimize", payload);
  return response.data;
}

// ============================================================
// RUNS
// ============================================================

export async function getLatestRun() {
  const response = await api.get("/runs/latest");
  return response.data;
}

export async function getLatestCompletedRun() {
  const response = await api.get("/runs/latest-completed");
  return response.data;
}

export async function getRun(runId) {
  if (!runId) throw new Error("runId is required.");
  const response = await api.get(
    `/runs/${encodeURIComponent(runId)}`,
  );
  return response.data;
}

// ============================================================
// KPIs
// ============================================================

export async function getKpis(runId) {
  if (!runId) throw new Error("runId is required.");
  const response = await api.get(
    `/kpis/${encodeURIComponent(runId)}`,
  );
  return response.data;
}

// ============================================================
// PRODUCTION PLAN
// ============================================================

export async function explainPlanningOperation(runId, operationId) {
  if (!runId) throw new Error("runId is required.");
  if (!operationId) throw new Error("operationId is required.");

  const response = await api.get(
    `/planning/${encodeURIComponent(runId)}/operations/${encodeURIComponent(operationId)}/explain`,
  );

  return response.data;
}

export async function getPlanning(runId) {
  if (!runId) throw new Error("runId is required.");
  const response = await api.get(
    `/planning/${encodeURIComponent(runId)}`,
  );
  return response.data;
}


// ============================================================
// PROCUREMENT PLAN
// ============================================================

export async function getProcurement(runId) {
  if (!runId) throw new Error("runId is required.");
  const response = await api.get(
    `/procurement/${encodeURIComponent(runId)}`,
  );
  return response.data;
}

export async function updatePlanningOperation(
  runId,
  operationId,
  payload,
) {
  if (!runId) {
    throw new Error("runId is required.");
  }

  if (!operationId) {
    throw new Error("operationId is required.");
  }

  const response = await api.put(
    `/planning/${encodeURIComponent(runId)}/operations/${encodeURIComponent(operationId)}`,
    payload,
  );

  return response.data;
}
// ============================================================
// HEALTH
// ============================================================

export async function healthCheck() {
  const response = await api.get("/health");
  return response.data;
}

// ============================================================
// ORDERS
// ============================================================

export async function getOrders(params = {}) {
  const response = await api.get("/orders", { params });
  return response.data;
}

export async function getOrderRisk(params = {}) {
  const response = await api.get("/orders/risk", { params });
  return response.data;
}

// ============================================================
// MACHINES
// ============================================================

export async function getMachines(params = {}) {
  const response = await api.get("/machines", { params });
  return response.data;
}

// ============================================================
// MACHINE CALENDAR
// ============================================================
export async function getMachineCalendar(params = {}) {
  const response = await api.get("/machine-calendar", { params });
  return response.data;
}

// ============================================================
// MATERIALS
// ============================================================

export async function getMaterials(params = {}) {
  const safeParams = {
    ...params,
    limit: Math.min(Number(params.limit ?? 500), 500),
  };
  const response = await api.get("/materials", { params: safeParams });
  return response.data;
}

// ============================================================
// MATERIAL SHORTAGE PREDICTION
// ============================================================

export async function getShortagePrediction(materialId, params = {}) {
  if (!materialId) {
    throw new Error("materialId is required.");
  }

  const response = await api.get(
    `/shortage-prediction/${encodeURIComponent(materialId)}`,
    {
      params,
    },
  );

  return response.data;
}

export async function getAllShortagePredictions(materialIds, params = {}) {
  if (!Array.isArray(materialIds) || materialIds.length === 0) {
    return [];
  }

  const predictions = await Promise.all(
    materialIds.map(async (materialId) => {
      try {
        return await getShortagePrediction(materialId, params);
      } catch (error) {
        console.error(
          `Shortage prediction failed for ${materialId}:`,
          error,
        );

        return {
          material_id: materialId,
          prediction_error:
            error.response?.data?.detail ||
            error.message ||
            "Prediction unavailable",
        };
      }
    }),
  );

  return predictions;
}



// ============================================================
// PRODUCTS
// ============================================================

export async function getProducts(params = {}) {
  const response = await api.get("/products", { params });
  return response.data;
}

export async function getProduct(productId) {
  if (!productId) throw new Error("productId is required.");
  const response = await api.get(
    `/products/${encodeURIComponent(productId)}`,
  );
  return response.data;
}

// ============================================================
// DATA IMPORT
// ============================================================

export async function importDataset(file, datasetKey) {
  if (!file) throw new Error("No file selected.");
  if (!datasetKey) throw new Error("datasetKey is required.");

  const formData = new FormData();
  formData.append("dataset_key", datasetKey);
  formData.append("file", file);

  const response = await api.post("/data/import", formData);
  return response.data;
}

export async function getDataQuality() {
  const response = await api.get("/data/quality");
  return response.data;
}

// ============================================================
// SCENARIOS
// ============================================================

export async function createUrgentOrder(payload) {
  const response = await api.post("/orders", payload);
  return response.data;
}

export async function createBreakdown(machineId, payload) {
  if (!machineId) throw new Error("machineId is required.");

  const response = await api.post(
    `/machines/${encodeURIComponent(machineId)}/breakdown`,
    payload,
  );
  return response.data;
}

// ============================================================
// PLANNING ASSISTANT
// ============================================================

export async function askAssistant(question, runId = null) {
  if (!question?.trim()) throw new Error("question is required.");
  const response = await api.post("/assistant/ask", {
    question: question.trim(),
    run_id: runId || undefined,
  });
  return response.data;
}

export default api;
