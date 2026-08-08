const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const TOKEN_KEY = "sqlscribe_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse(res) {
  if (!res.ok) {
    let detail = "Request failed.";
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — keep default message
    }
    const error = new Error(detail);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function signup(username, password) {
  const res = await fetch(`${API_BASE}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await handleResponse(res);
  setToken(data.token);
  return data;
}

export async function login(username, password) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await handleResponse(res);
  setToken(data.token);
  return data;
}

export async function logout() {
  const res = await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    headers: authHeaders(),
  });
  clearToken();
  // Don't throw on a failed logout call — we're clearing the local token
  // either way, so the user ends up signed out client-side regardless.
  if (!res.ok) return { ok: false };
  return res.json();
}

export async function fetchMe() {
  const res = await fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Data source
// ---------------------------------------------------------------------------

export async function fetchSource() {
  const res = await fetch(`${API_BASE}/api/source`, { headers: authHeaders() });
  return handleResponse(res);
}

export async function connectDemo() {
  const res = await fetch(`${API_BASE}/api/source/demo`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function connectPostgres({ host, port, database, user, password }) {
  const res = await fetch(`${API_BASE}/api/source/postgres`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ host, port: Number(port), database, user, password }),
  });
  return handleResponse(res);
}

export async function connectMysql({ host, port, database, user, password }) {
  const res = await fetch(`${API_BASE}/api/source/mysql`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ host, port: Number(port), database, user, password }),
  });
  return handleResponse(res);
}

export async function connectSqlitePath(path) {
  const res = await fetch(`${API_BASE}/api/source/sqlite-path`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ path }),
  });
  return handleResponse(res);
}

export async function connectSqlite(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/source/sqlite`, {
    method: "POST",
    headers: authHeaders(), // do NOT set Content-Type here - browser sets the multipart boundary
    body: formData,
  });
  return handleResponse(res);
}

export async function disconnectSource() {
  const res = await fetch(`${API_BASE}/api/source/disconnect`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function fetchSchema() {
  const res = await fetch(`${API_BASE}/api/schema`, { headers: authHeaders() });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Table descriptions ("meta table") — LLM-generated, per-table
// descriptions that enrich both the Schema tab UI and the prompt context
// sent to the model for SQL generation.
// ---------------------------------------------------------------------------

export async function fetchTableDescriptions() {
  const res = await fetch(`${API_BASE}/api/schema/descriptions`, { headers: authHeaders() });
  return handleResponse(res);
}

export async function generateTableDescriptions(overwriteCustom = false) {
  const query = overwriteCustom ? "?overwrite_custom=true" : "";
  const res = await fetch(`${API_BASE}/api/schema/descriptions/generate${query}`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function setTableDescription(tableName, description) {
  const res = await fetch(`${API_BASE}/api/schema/descriptions/${encodeURIComponent(tableName)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ description }),
  });
  return handleResponse(res);
}

export async function clearTableDescription(tableName) {
  const res = await fetch(`${API_BASE}/api/schema/descriptions/${encodeURIComponent(tableName)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function setColumnDescription(tableName, columnName, description) {
  const res = await fetch(
    `${API_BASE}/api/schema/descriptions/${encodeURIComponent(tableName)}/columns/${encodeURIComponent(columnName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ description }),
    }
  );
  return handleResponse(res);
}

export async function clearColumnDescription(tableName, columnName) {
  const res = await fetch(
    `${API_BASE}/api/schema/descriptions/${encodeURIComponent(tableName)}/columns/${encodeURIComponent(columnName)}`,
    {
      method: "DELETE",
      headers: authHeaders(),
    }
  );
  return handleResponse(res);
}


export async function runQuery(question) {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question }),
  });
  return handleResponse(res);
}

// Executes a write query (INSERT/UPDATE/DELETE/DDL) the user has already
// reviewed and explicitly confirmed. Only called after runQuery() comes
// back with pending_confirmation: true — never on the initial ask.
export async function confirmQuery(question, sql) {
  const res = await fetch(`${API_BASE}/api/query/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, sql }),
  });
  return handleResponse(res);
}

export async function fetchHistory(limit = 10, databaseName = null) {
  let url = `${API_BASE}/api/history?limit=${limit}`;
  if (databaseName) {
    url += `&database_name=${encodeURIComponent(databaseName)}`;
  }
  const res = await fetch(url, { headers: authHeaders() });
  return handleResponse(res);
}

export async function setHistoryFavorite(id, isFavorite) {
  const res = await fetch(`${API_BASE}/api/history/${id}/favorite`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ is_favorite: isFavorite }),
  });
  return handleResponse(res);
}

export async function deleteHistoryEntry(id) {
  const res = await fetch(`${API_BASE}/api/history/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function clearHistory(databaseName = null) {
  let url = `${API_BASE}/api/history`;
  if (databaseName) {
    url += `?database_name=${encodeURIComponent(databaseName)}`;
  }
  const res = await fetch(url, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse(res);
}