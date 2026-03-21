/**
 * Converter Agent — API client
 * Endpoint stubs for future backend (FastAPI @ localhost:8000)
 *
 * All functions try the real backend first; on failure they fall back to
 * mock data so the UI keeps working without a running server.
 */

const API_BASE = 'http://localhost:8000/api/v1';

// ── helpers ──────────────────────────────────────────────────────────────────

function _token() {
  try { return (getSession() || {}).token || ''; } catch { return ''; }
}

function _authHeaders() {
  return { 'Authorization': 'Bearer ' + _token() };
}

// ── endpoints ─────────────────────────────────────────────────────────────────

const Api = {

  /**
   * POST /api/v1/prediction/upload
   * Upload a file and target JSON schema to start a conversion job.
   *
   * @param {File}   file         – the source file (CSV / XLS / PDF / etc.)
   * @param {string} targetSchema – target JSON schema string
   * @returns {Promise<{job_id: string, status: string}>}
   */
  async upload(file, targetSchema) {
    const form = new FormData();
    form.append('file', file);
    form.append('target_json_schema', targetSchema);

    try {
      const res = await fetch(`${API_BASE}/prediction/upload`, {
        method: 'POST',
        headers: _authHeaders(),
        body: form,
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      // Backend unavailable — return a mock pending job
      return {
        job_id: 'mock_' + Math.random().toString(36).slice(2, 10),
        status: 'pending',
        _mock: true,
      };
    }
  },

  /**
   * GET /api/v1/prediction/{job_id}
   * Poll the status of a conversion job.
   *
   * @param {string} jobId
   * @returns {Promise<{status: string, ts_code?: string, records?: object[], tokens?: number, retries?: number} | null>}
   */
  async pollJob(jobId) {
    try {
      const res = await fetch(`${API_BASE}/prediction/${jobId}`, {
        headers: _authHeaders(),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return null; // Backend unavailable
    }
  },

  /**
   * GET /api/v1/prediction/
   * List all conversion jobs for the current user.
   *
   * @returns {Promise<Array>}
   */
  async listJobs() {
    try {
      const res = await fetch(`${API_BASE}/prediction/`, {
        headers: _authHeaders(),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return [];
    }
  },

  /**
   * GET /api/v1/history/
   * Fetch conversion history for the current user.
   *
   * @returns {Promise<Array>}
   */
  async getHistory() {
    try {
      const res = await fetch(`${API_BASE}/history/`, {
        headers: _authHeaders(),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return [];
    }
  },

  /**
   * POST /api/v1/auth/login
   * Authenticate and receive a JWT token.
   *
   * @param {string} email
   * @param {string} password
   * @returns {Promise<{access_token: string, token_type: string} | null>}
   */
  async login(email, password) {
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return null; // Backend unavailable — auth.js mock takes over
    }
  },

  /**
   * GET /api/v1/auth/me
   * Return the currently authenticated user's profile.
   *
   * @returns {Promise<object | null>}
   */
  async me() {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: _authHeaders(),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return null;
    }
  },
};
