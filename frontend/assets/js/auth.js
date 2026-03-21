/**
 * auth.js — Login / Register logic
 * Endpoints (mock → заменить на fetch при наличии бека):
 *   POST /api/v1/auth/login      { email, password }  → { token, user }
 *   POST /api/v1/auth/register   { name, email, password } → { user }
 *   POST /api/v1/auth/logout
 *   PATCH /api/v1/users/:id/photo { photo: base64 }
 */

// ── Tab switching ──
function switchTab(tab) {
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
  document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
  document.getElementById('form-' + tab).classList.add('active');
  clearAlert();
}

// ── Alert helpers ──
function showAlert(msg, type = 'err') {
  const el = document.getElementById('authAlert');
  el.className = 'alert alert-' + type;
  el.textContent = msg;
  el.style.display = 'flex';
}
function clearAlert() {
  const el = document.getElementById('authAlert');
  if (el) el.style.display = 'none';
}

// ── LOGIN ──
async function doLogin() {
  clearAlert();
  const email    = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;

  if (!email)    { showAlert('Введите email'); return; }
  if (!password) { showAlert('Введите пароль'); return; }

  try {
    const data = await Api.auth.login(email, password);
    // data: { access_token, token_type, expires_in, user: {id, name, email, role, photo, createdAt} }
    localStorage.setItem('sber_session', JSON.stringify({
      userId:    data.user.id,
      name:      data.user.name,
      email:     data.user.email,
      role:      data.user.role,
      photo:     data.user.photo,
      token:     data.access_token,
      expiresAt: new Date(Date.now() + data.expires_in * 1000).toISOString(),
    }));
    window.location.href = 'dashboard.html';
  } catch (err) {
    showAlert(err.message || 'Неверный email или пароль');
  }

// ── REGISTER ──
async function doRegister() {
  clearAlert();
  const name     = document.getElementById('regName').value.trim();
  const email    = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;
  const confirm  = document.getElementById('regConfirm').value;

  if (!name)     { showAlert('Введите имя'); return; }
  if (!email)    { showAlert('Введите email'); return; }
  if (!email.includes('@')) { showAlert('Некорректный email'); return; }
  if (password.length < 6) { showAlert('Пароль минимум 6 символов'); return; }
  if (password !== confirm) { showAlert('Пароли не совпадают'); return; }

  try {
    const data = await Api.auth.register(name, email, password);
    localStorage.setItem('sber_session', JSON.stringify({
      userId:    data.user.id,
      name:      data.user.name,
      email:     data.user.email,
      role:      data.user.role,
      photo:     data.user.photo,
      token:     data.access_token,
      expiresAt: new Date(Date.now() + data.expires_in * 1000).toISOString(),
    }));
    showAlert('Аккаунт создан! Перенаправляем...', 'ok');
    setTimeout(() => { window.location.href = 'profile.html?new=1'; }, 1200);
  } catch (err) {
    showAlert(err.message || 'Ошибка при регистрации');
  }
}

// ── LOGOUT (вызывается из dashboard/profile) ──
function logout() {
  if (typeof window.__showLogoutModal === 'function') {
    window.__showLogoutModal();
  } else {
    if (!confirm('Выйти из аккаунта?')) return;
    clearSession();
    window.location.href = 'index.html';
  }
}

function _doLogout() {
  if (typeof Api !== 'undefined') {
    Api.auth.logout().catch(() => {});  // fire-and-forget
  }
  clearSession();
  window.location.href = 'index.html';
}

// ── PHOTO UPLOAD ──
function handlePhotoUpload(inputEl) {
  const file = inputEl.files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { alert('Файл слишком большой (макс. 5 MB)'); return; }

  const reader = new FileReader();
  reader.onload = function(e) {
    const base64 = e.target.result;

    // Save to storage
    const session = getSession();
    if (session) {
      updateUserPhoto(session.userId, base64);
      refreshSessionPhoto(base64);
    }

    // Update all avatar elements on page
    document.querySelectorAll('.avatar-preview').forEach(img => {
      if (img.tagName === 'IMG') {
        img.src = base64;
        img.style.display = 'block';
      }
    });
    document.querySelectorAll('.avatar-placeholder-el').forEach(el => {
      el.style.display = 'none';
    });
    document.querySelectorAll('.user-pill-avatar').forEach(el => {
      if (el.tagName === 'IMG') {
        el.src = base64;
      } else {
        // Replace div with img
        const img = document.createElement('img');
        img.src = base64;
        img.className = 'user-pill-avatar';
        img.style.cssText = 'width:28px;height:28px;border-radius:50%;object-fit:cover;';
        el.replaceWith(img);
      }
    });

    showToast('Фото успешно обновлено');
  };
  reader.readAsDataURL(file);
}

// ── TOAST ──
function showToast(msg) {
  let toast = document.getElementById('sberToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'sberToast';
    toast.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:9999;
      background:linear-gradient(90deg,#01a104,#16da03);
      color:#fff; padding:12px 20px; border-radius:10px;
      font-size:14px; font-weight:600; box-shadow:0 4px 20px rgba(0,0,0,0.4);
      transition: opacity .3s;
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => { toast.style.opacity = '0'; }, 3000);
}

// ── Guard: redirect to login if no session ──
function requireAuth() {
  if (!getSession()) {
    window.location.href = 'index.html';
    return false;
  }
  return true;
}

// ── Fill topbar user pill ──
function fillTopbarUser() {
  const session = getSession();
  if (!session) return;

  const nameEl = document.getElementById('topbarUserName');
  if (nameEl) nameEl.textContent = session.name;

  document.querySelectorAll('.user-pill-avatar').forEach(el => {
    if (session.photo) {
      if (el.tagName === 'IMG') {
        el.src = session.photo;
      } else {
        el.style.backgroundImage = `url(${session.photo})`;
        el.style.backgroundSize = 'cover';
        el.textContent = '';
      }
    } else {
      const initials = session.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
      if (el.tagName !== 'IMG') el.textContent = initials;
    }
  });
}
