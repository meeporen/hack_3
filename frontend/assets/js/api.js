/**
 * api.js — Real API client
 * Заменяет storage.js mock-вызовы на реальные fetch() к FastAPI бекенду.
 *
 * Использование:
 *   const res = await Api.auth.login(email, password);
 *   const res = await Api.prediction.upload(file, schema);
 *   const res = await Api.history.list();
 */

const BASE_URL = '';   // Пустая строка = тот же origin (FastAPI раздаёт фронт)

function getToken() {
  const session = JSON.parse(localStorage.getItem('sber_session') || 'null');
  return session?.token || null;
}

async function request(method, path, body = null, isFormData = false) {
  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!isFormData && body) headers['Content-Type'] = 'application/json';

  const res = await fetch(BASE_URL + path, {
    method,
    headers,
    body: isFormData ? body : (body ? JSON.stringify(body) : null),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

const Api = {
  // ── Auth ──────────────────────────────────────────────────────────
  auth: {
    /** POST /api/v1/auth/login → TokenResponse */
    login: (email, password) =>
      request('POST', '/api/v1/auth/login', { email, password }),

    /** POST /api/v1/auth/register → TokenResponse */
    register: (name, email, password) =>
      request('POST', '/api/v1/auth/register', { name, email, password }),

    /** POST /api/v1/auth/logout */
    logout: () =>
      request('POST', '/api/v1/auth/logout'),

    /** GET /api/v1/auth/me → UserOut */
    me: () =>
      request('GET', '/api/v1/auth/me'),

    /** PATCH /api/v1/auth/photo → UserOut */
    updatePhoto: (photoBase64) =>
      request('PATCH', '/api/v1/auth/photo', { photo: photoBase64 }),
  },

  // ── Prediction / Conversion ───────────────────────────────────────
  prediction: {
    /**
     * POST /api/v1/prediction/upload
     * @param {File} file
     * @param {object} targetSchema
     * @returns {Promise<ConvertResponse>}
     */
    upload: (file, targetSchema) => {
      const form = new FormData();
      form.append('file', file);
      form.append('target_schema', JSON.stringify(targetSchema));
      return request('POST', '/api/v1/prediction/upload', form, true);
    },

    /** GET /api/v1/prediction/{job_id} → JobResult */
    getJob: (jobId) =>
      request('GET', `/api/v1/prediction/${jobId}`),

    /** GET /api/v1/prediction → JobResult[] */
    listJobs: () =>
      request('GET', '/api/v1/prediction'),

    /**
     * Poll job until done or error.
     * @param {string} jobId
     * @param {function} onUpdate - callback(JobResult) на каждый poll
     * @param {number} intervalMs - интервал опроса
     */
    pollJob: async (jobId, onUpdate, intervalMs = 1500) => {
      return new Promise((resolve, reject) => {
        const timer = setInterval(async () => {
          try {
            const job = await Api.prediction.getJob(jobId);
            onUpdate(job);
            if (job.status === 'done' || job.status === 'error') {
              clearInterval(timer);
              job.status === 'done' ? resolve(job) : reject(new Error(job.error));
            }
          } catch (err) {
            clearInterval(timer);
            reject(err);
          }
        }, intervalMs);
      });
    },
  },

  // ── History ───────────────────────────────────────────────────────
  history: {
    /** GET /api/v1/history → HistoryListResponse */
    list: () =>
      request('GET', '/api/v1/history'),

    /** DELETE /api/v1/history/{id} */
    delete: (id) =>
      request('DELETE', `/api/v1/history/${id}`),

    /** DELETE /api/v1/history */
    clear: () =>
      request('DELETE', '/api/v1/history'),
  },

  // ── Chat WebSocket ────────────────────────────────────────────────
  chat: {
    /**
     * Открыть WebSocket соединение с чатом.
     * @param {function} onChunk - callback(text) для каждого chunk
     * @param {function} onDone  - callback(tokens) при завершении
     * @returns {object} { send(message), close() }
     */
    connect: (onChunk, onDone) => {
      const token = getToken();
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/api/v1/chat/ws?token=${token}`);

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'chunk') onChunk(data.text);
        if (data.type === 'done')  onDone(data.tokens);
      };

      return {
        send:  (msg) => ws.send(JSON.stringify({ message: msg })),
        close: ()    => ws.close(),
      };
    },
  },
};
