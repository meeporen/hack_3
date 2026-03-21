/**
 * storage.js — Mock JSON storage (localStorage)
 * Эмулирует backend API. При реальном беке заменить на fetch() вызовы.
 */

const STORAGE_KEY = 'sber_users';
const SESSION_KEY = 'sber_session';

// Seed initial mock users if storage is empty
const SEED_USERS = [
  { id: 1, name: 'Иван Иванов',   email: 'ivan@sber.ru',  password: 'password', role: 'admin', photo: null, createdAt: '2026-01-10T10:00:00.000Z' },
  { id: 2, name: 'Анна Петрова',  email: 'anna@sber.ru',  password: 'password', role: 'user',  photo: null, createdAt: '2026-02-15T09:30:00.000Z' }
];

function initStorage() {
  if (!localStorage.getItem(STORAGE_KEY)) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(SEED_USERS));
  }
}

function getUsers() {
  initStorage();
  return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
}

function saveUsers(users) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(users));
}

function getUserByEmail(email) {
  return getUsers().find(u => u.email.toLowerCase() === email.toLowerCase()) || null;
}

function getUserById(id) {
  return getUsers().find(u => u.id === id) || null;
}

function createUser(name, email, password) {
  const users = getUsers();
  if (getUserByEmail(email)) {
    return { ok: false, error: 'Пользователь с таким email уже существует' };
  }
  const newUser = {
    id: Date.now(),
    name,
    email,
    password,
    role: 'user',
    photo: null,
    createdAt: new Date().toISOString()
  };
  users.push(newUser);
  saveUsers(users);
  return { ok: true, user: { ...newUser, password: undefined } };
}

function updateUserPhoto(userId, photoBase64) {
  const users = getUsers();
  const idx = users.findIndex(u => u.id === userId);
  if (idx === -1) return { ok: false, error: 'Пользователь не найден' };
  users[idx].photo = photoBase64;
  saveUsers(users);
  return { ok: true };
}

// ── Session ──
function saveSession(user) {
  const session = {
    userId: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    photo: user.photo,
    // Mock JWT token (при реальном беке — настоящий токен)
    token: 'mock_jwt_' + btoa(user.email + ':' + Date.now()),
    expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

function getSession() {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  const session = JSON.parse(raw);
  if (new Date(session.expiresAt) < new Date()) {
    clearSession();
    return null;
  }
  return session;
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function refreshSessionPhoto(photoBase64) {
  const session = getSession();
  if (!session) return;
  session.photo = photoBase64;
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}
