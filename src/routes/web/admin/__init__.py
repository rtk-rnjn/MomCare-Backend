from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse

from src.app import app

ADMIN_DASHBOARD_DIR = Path(__file__).parent.parent.parent.parent / "admin-dashboard" / "dist"


@app.get("/admin-dashboard", include_in_schema=False)
@app.get("/admin-dashboard/{path:path}", include_in_schema=False)
async def admin_dashboard(request: Request, path: str = ""):
    if ADMIN_DASHBOARD_DIR.exists():
        # Try to serve the requested file
        requested_file = ADMIN_DASHBOARD_DIR / path
        if requested_file.is_file():
            return FileResponse(requested_file)
        # For SPA routing, always serve index.html
        index_file = ADMIN_DASHBOARD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

    # Fallback: serve inline admin SPA
    return HTMLResponse(content=_get_admin_spa_html(), status_code=200)


def _get_admin_spa_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MomCare Admin Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  .sidebar-link { @apply flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200; }
  .sidebar-link:hover { @apply bg-indigo-50 text-indigo-700; }
  .sidebar-link.active { @apply bg-indigo-100 text-indigo-800 font-semibold; }
  .card { @apply bg-white rounded-xl shadow-sm border border-gray-100 p-6; }
  .btn-primary { @apply bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50; }
  .btn-danger { @apply bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50; }
  .btn-secondary { @apply bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors; }
  .input-field { @apply w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all; }
  .table-header { @apply px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider; }
  .table-cell { @apply px-4 py-3 text-sm text-gray-700; }
  .badge { @apply inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium; }
  .badge-green { @apply bg-green-100 text-green-800; }
  .badge-red { @apply bg-red-100 text-red-800; }
  .badge-yellow { @apply bg-yellow-100 text-yellow-800; }
  .badge-blue { @apply bg-blue-100 text-blue-800; }
  .badge-purple { @apply bg-purple-100 text-purple-800; }
  .modal-overlay { @apply fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50; }
  .modal-content { @apply bg-white rounded-xl shadow-2xl p-6 max-w-md w-full mx-4; }
  .tab-btn { @apply px-4 py-2 text-sm font-medium rounded-lg transition-colors; }
  .tab-btn.active { @apply bg-indigo-600 text-white; }
  .tab-btn:not(.active) { @apply text-gray-600 hover:bg-gray-100; }
</style>
</head>
<body class="bg-gray-50">
<div id="admin-root"></div>
<script type="text/babel">
const { useState, useEffect, useCallback, useRef, createContext, useContext } = React;

// ============ API Client ============
const API_BASE = '/api/admin';

const apiClient = {
  token: localStorage.getItem('admin_token'),
  refreshToken: localStorage.getItem('admin_refresh_token'),

  setTokens(access, refresh) {
    this.token = access;
    this.refreshToken = refresh;
    localStorage.setItem('admin_token', access);
    localStorage.setItem('admin_refresh_token', refresh);
  },

  clearTokens() {
    this.token = null;
    this.refreshToken = null;
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_refresh_token');
    localStorage.removeItem('admin_user');
  },

  async request(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (this.token) headers['Authorization'] = `Bearer ${this.token}`;

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401 && this.refreshToken) {
      const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });
      if (refreshRes.ok) {
        const data = await refreshRes.json();
        this.setTokens(data.access_token, data.refresh_token);
        headers['Authorization'] = `Bearer ${this.token}`;
        const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (!retry.ok) throw new Error((await retry.json()).detail || 'Request failed');
        return retry.json();
      }
      this.clearTokens();
      window.location.hash = '#/login';
      throw new Error('Session expired');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(err.detail || 'Request failed');
    }
    return res.json();
  },

  get: (path) => apiClient.request(path),
  post: (path, body) => apiClient.request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => apiClient.request(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: (path, body) => apiClient.request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path) => apiClient.request(path, { method: 'DELETE' }),
};

// ============ Auth Context ============
const AuthContext = createContext(null);

function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('admin_user')); } catch { return null; }
  });
  const [loading, setLoading] = useState(false);

  const login = async (username, password) => {
    setLoading(true);
    try {
      const data = await apiClient.post('/auth/login', { username, password });
      apiClient.setTokens(data.access_token, data.refresh_token);
      const me = await apiClient.get('/auth/me');
      setUser(me);
      localStorage.setItem('admin_user', JSON.stringify(me));
      return me;
    } finally { setLoading(false); }
  };

  const logout = async () => {
    try {
      await apiClient.post('/auth/logout', { refresh_token: apiClient.refreshToken });
    } catch {}
    apiClient.clearTokens();
    setUser(null);
  };

  return React.createElement(AuthContext.Provider, { value: { user, login, logout, loading, isSuperAdmin: user?.role === 'super_admin' } }, children);
}

const useAuth = () => useContext(AuthContext);

// ============ Router ============
function useHashRouter() {
  const [hash, setHash] = useState(window.location.hash || '#/login');
  useEffect(() => {
    const handler = () => setHash(window.location.hash || '#/login');
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);
  return hash.replace('#', '') || '/login';
}

function navigate(path) { window.location.hash = '#' + path; }

// ============ Confirm Modal ============
function ConfirmModal({ open, title, message, onConfirm, onCancel, danger }) {
  if (!open) return null;
  return React.createElement('div', { className: 'modal-overlay', onClick: onCancel },
    React.createElement('div', { className: 'modal-content', onClick: e => e.stopPropagation() },
      React.createElement('h3', { className: 'text-lg font-semibold mb-2' }, title),
      React.createElement('p', { className: 'text-gray-600 text-sm mb-6' }, message),
      React.createElement('div', { className: 'flex gap-3 justify-end' },
        React.createElement('button', { className: 'btn-secondary', onClick: onCancel }, 'Cancel'),
        React.createElement('button', { className: danger ? 'btn-danger' : 'btn-primary', onClick: onConfirm }, 'Confirm')
      )
    )
  );
}

// ============ Pagination ============
function Pagination({ page, total, perPage, onPageChange }) {
  const totalPages = Math.ceil(total / perPage);
  if (totalPages <= 1) return null;
  return React.createElement('div', { className: 'flex items-center justify-between mt-4' },
    React.createElement('span', { className: 'text-sm text-gray-500' }, `Page ${page} of ${totalPages} (${total} items)`),
    React.createElement('div', { className: 'flex gap-2' },
      React.createElement('button', { className: 'btn-secondary', disabled: page <= 1, onClick: () => onPageChange(page - 1) }, 'Previous'),
      React.createElement('button', { className: 'btn-secondary', disabled: page >= totalPages, onClick: () => onPageChange(page + 1) }, 'Next')
    )
  );
}

// ============ Login Page ============
function LoginPage() {
  const { login, loading } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await login(username, password);
      navigate('/dashboard');
    } catch (err) { setError(err.message); }
  };

  return React.createElement('div', { className: 'min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 to-purple-50' },
    React.createElement('div', { className: 'card max-w-md w-full mx-4' },
      React.createElement('div', { className: 'text-center mb-8' },
        React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, '🤱 MomCare Admin'),
        React.createElement('p', { className: 'text-gray-500 mt-1' }, 'Sign in to your admin account')
      ),
      error && React.createElement('div', { className: 'bg-red-50 text-red-700 p-3 rounded-lg text-sm mb-4' }, error),
      React.createElement('form', { onSubmit: handleSubmit },
        React.createElement('div', { className: 'space-y-4' },
          React.createElement('input', { className: 'input-field', placeholder: 'Username', value: username, onChange: e => setUsername(e.target.value), required: true }),
          React.createElement('input', { className: 'input-field', type: 'password', placeholder: 'Password', value: password, onChange: e => setPassword(e.target.value), required: true }),
          React.createElement('button', { className: 'btn-primary w-full', type: 'submit', disabled: loading }, loading ? 'Signing in...' : 'Sign In')
        )
      )
    )
  );
}

// ============ Sidebar ============
function Sidebar({ currentPath }) {
  const { user, logout, isSuperAdmin } = useAuth();

  const links = [
    { path: '/dashboard', icon: '📊', label: 'Dashboard' },
    { path: '/users', icon: '👥', label: 'Users' },
    { path: '/models/exercises', icon: '🏋️', label: 'Exercises' },
    { path: '/models/foods', icon: '🍎', label: 'Foods' },
    { path: '/models/songs', icon: '🎵', label: 'Songs' },
    { path: '/logs', icon: '📈', label: 'Logs & Analytics' },
    { path: '/db/redis', icon: '🔴', label: 'Redis Tools' },
    { path: '/db/mongo', icon: '🍃', label: 'MongoDB Tools' },
    { path: '/system', icon: '⚙️', label: 'System' },
  ];
  if (isSuperAdmin) links.push({ path: '/admins', icon: '🔐', label: 'Admin Management' });

  return React.createElement('aside', { className: 'w-64 bg-white border-r border-gray-100 min-h-screen flex flex-col' },
    React.createElement('div', { className: 'p-6 border-b border-gray-100' },
      React.createElement('h2', { className: 'text-lg font-bold text-gray-900' }, '🤱 MomCare'),
      React.createElement('p', { className: 'text-xs text-gray-500 mt-1' }, 'Admin Dashboard')
    ),
    React.createElement('nav', { className: 'flex-1 p-4 space-y-1' },
      links.map(l => React.createElement('a', {
        key: l.path, href: '#' + l.path,
        className: `sidebar-link ${currentPath.startsWith(l.path) ? 'active' : ''}`
      }, React.createElement('span', null, l.icon), l.label))
    ),
    React.createElement('div', { className: 'p-4 border-t border-gray-100' },
      React.createElement('div', { className: 'flex items-center gap-3 mb-3' },
        React.createElement('div', { className: 'w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center text-sm font-bold text-indigo-700' }, user?.username?.[0]?.toUpperCase()),
        React.createElement('div', null,
          React.createElement('div', { className: 'text-sm font-medium' }, user?.username),
          React.createElement('div', { className: `badge ${user?.role === 'super_admin' ? 'badge-purple' : 'badge-blue'}` }, user?.role)
        )
      ),
      React.createElement('button', { className: 'btn-secondary w-full text-center', onClick: () => { logout(); navigate('/login'); } }, 'Sign Out')
    )
  );
}

// ============ Dashboard Page ============
function DashboardPage() {
  const [data, setData] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const chartRef = useRef(null);
  const chartInstance = useRef(null);

  useEffect(() => {
    apiClient.get('/system/dashboard').then(setData).catch(() => {});
    apiClient.get('/logs/analytics').then(setAnalytics).catch(() => {});
  }, []);

  useEffect(() => {
    if (!analytics || !chartRef.current) return;
    if (chartInstance.current) chartInstance.current.destroy();
    const cats = analytics.categories || {};
    chartInstance.current = new Chart(chartRef.current, {
      type: 'doughnut',
      data: {
        labels: ['2xx Success', '3xx Redirect', '4xx Client Error', '5xx Server Error'],
        datasets: [{
          data: [cats['2xx']?.count || 0, cats['3xx']?.count || 0, cats['4xx']?.count || 0, cats['5xx']?.count || 0],
          backgroundColor: ['#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
        }],
      },
      options: { responsive: true, plugins: { legend: { position: 'bottom' } } },
    });
    return () => { if (chartInstance.current) chartInstance.current.destroy(); };
  }, [analytics]);

  if (!data) return React.createElement('div', { className: 'p-8 text-gray-500' }, 'Loading...');

  const cards = [
    { label: 'Version', value: data.version, icon: '🏷️' },
    { label: 'Uptime', value: `${Math.floor(data.uptime_seconds / 3600)}h ${Math.floor((data.uptime_seconds % 3600) / 60)}m`, icon: '⏱️' },
    { label: 'Total Users', value: data.users?.total || 0, icon: '👥' },
    { label: 'Total Requests', value: data.requests?.total || 0, icon: '📊' },
    { label: 'Error Rate (1h)', value: `${data.requests?.error_rate_percent || 0}%`, icon: '⚠️' },
    { label: 'Memory', value: `${data.system?.memory_rss_mb || 0} MB`, icon: '💾' },
  ];

  return React.createElement('div', { className: 'space-y-6' },
    React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Dashboard'),
    React.createElement('div', { className: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4' },
      cards.map((c, i) => React.createElement('div', { key: i, className: 'card flex items-center gap-4' },
        React.createElement('div', { className: 'text-2xl' }, c.icon),
        React.createElement('div', null,
          React.createElement('div', { className: 'text-sm text-gray-500' }, c.label),
          React.createElement('div', { className: 'text-xl font-bold text-gray-900' }, c.value)
        )
      ))
    ),
    React.createElement('div', { className: 'grid grid-cols-1 lg:grid-cols-2 gap-6' },
      React.createElement('div', { className: 'card' },
        React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Status Code Distribution'),
        React.createElement('canvas', { ref: chartRef, height: 250 })
      ),
      React.createElement('div', { className: 'card' },
        React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'System Health'),
        React.createElement('div', { className: 'space-y-3' },
          React.createElement('div', { className: 'flex items-center justify-between p-3 bg-gray-50 rounded-lg' },
            React.createElement('span', { className: 'text-sm font-medium' }, 'Redis'),
            React.createElement('span', { className: `badge ${data.database?.redis_connected ? 'badge-green' : 'badge-red'}` }, data.database?.redis_connected ? 'Connected' : 'Disconnected')
          ),
          React.createElement('div', { className: 'flex items-center justify-between p-3 bg-gray-50 rounded-lg' },
            React.createElement('span', { className: 'text-sm font-medium' }, 'MongoDB'),
            React.createElement('span', { className: `badge ${data.database?.mongo_connected ? 'badge-green' : 'badge-red'}` }, data.database?.mongo_connected ? 'Connected' : 'Disconnected')
          ),
          React.createElement('div', { className: 'flex items-center justify-between p-3 bg-gray-50 rounded-lg' },
            React.createElement('span', { className: 'text-sm font-medium' }, 'Active Users'),
            React.createElement('span', { className: 'badge badge-blue' }, data.users?.active || 0)
          ),
          React.createElement('div', { className: 'flex items-center justify-between p-3 bg-gray-50 rounded-lg' },
            React.createElement('span', { className: 'text-sm font-medium' }, 'Locked Users'),
            React.createElement('span', { className: `badge ${data.users?.locked > 0 ? 'badge-yellow' : 'badge-green'}` }, data.users?.locked || 0)
          )
        )
      )
    )
  );
}

// ============ Users Page ============
function UsersPage() {
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [confirm, setConfirm] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page, per_page: 20 });
    if (search) params.set('search', search);
    const data = await apiClient.get(`/users/?${params}`);
    setUsers(data.items); setTotal(data.total);
  }, [page, search]);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (userId, action) => {
    try {
      if (action === 'lock') await apiClient.post(`/users/${userId}/lock`);
      else if (action === 'unlock') await apiClient.post(`/users/${userId}/unlock`);
      else if (action === 'delete') await apiClient.delete(`/users/${userId}`);
      setConfirm(null);
      load();
    } catch (err) { alert(err.message); }
  };

  const viewUser = async (userId) => {
    const data = await apiClient.get(`/users/${userId}`);
    setSelectedUser(data);
  };

  if (selectedUser) {
    return React.createElement('div', { className: 'space-y-4' },
      React.createElement('button', { className: 'btn-secondary', onClick: () => setSelectedUser(null) }, '← Back'),
      React.createElement('div', { className: 'card' },
        React.createElement('h2', { className: 'text-xl font-bold mb-4' }, 'User Details'),
        React.createElement('div', { className: 'grid grid-cols-2 gap-4' },
          Object.entries(selectedUser).map(([k, v]) =>
            React.createElement('div', { key: k, className: 'p-3 bg-gray-50 rounded-lg' },
              React.createElement('div', { className: 'text-xs text-gray-500 uppercase' }, k),
              React.createElement('div', { className: 'text-sm font-medium mt-1 break-all' }, typeof v === 'object' ? JSON.stringify(v) : String(v ?? 'N/A'))
            )
          )
        )
      )
    );
  }

  return React.createElement('div', { className: 'space-y-4' },
    React.createElement('div', { className: 'flex items-center justify-between' },
      React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, 'User Management'),
      React.createElement('div', { className: 'flex gap-3' },
        React.createElement('input', { className: 'input-field w-64', placeholder: 'Search users...', value: search, onChange: e => { setSearch(e.target.value); setPage(1); } })
      )
    ),
    React.createElement('div', { className: 'card overflow-x-auto' },
      React.createElement('table', { className: 'w-full' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'border-b border-gray-100' },
            ['Name', 'Email', 'Status', 'Verified', 'Actions'].map(h =>
              React.createElement('th', { key: h, className: 'table-header' }, h))
          )
        ),
        React.createElement('tbody', null,
          users.map(u => React.createElement('tr', { key: u._id, className: 'border-b border-gray-50 hover:bg-gray-50' },
            React.createElement('td', { className: 'table-cell font-medium' }, `${u.first_name || ''} ${u.last_name || ''}`),
            React.createElement('td', { className: 'table-cell' }, u.email_address || 'N/A'),
            React.createElement('td', { className: 'table-cell' },
              React.createElement('span', { className: `badge ${u.account_status === 'ACTIVE' ? 'badge-green' : u.account_status === 'LOCKED' ? 'badge-red' : 'badge-yellow'}` }, u.account_status || 'ACTIVE')
            ),
            React.createElement('td', { className: 'table-cell' },
              React.createElement('span', { className: `badge ${u.verified_email ? 'badge-green' : 'badge-yellow'}` }, u.verified_email ? 'Yes' : 'No')
            ),
            React.createElement('td', { className: 'table-cell' },
              React.createElement('div', { className: 'flex gap-2' },
                React.createElement('button', { className: 'text-indigo-600 hover:underline text-sm', onClick: () => viewUser(u._id) }, 'View'),
                u.account_status !== 'LOCKED'
                  ? React.createElement('button', { className: 'text-yellow-600 hover:underline text-sm', onClick: () => setConfirm({ id: u._id, action: 'lock', name: u.first_name }) }, 'Lock')
                  : React.createElement('button', { className: 'text-green-600 hover:underline text-sm', onClick: () => setConfirm({ id: u._id, action: 'unlock', name: u.first_name }) }, 'Unlock'),
                React.createElement('button', { className: 'text-red-600 hover:underline text-sm', onClick: () => setConfirm({ id: u._id, action: 'delete', name: u.first_name }) }, 'Delete')
              )
            )
          ))
        )
      ),
      React.createElement(Pagination, { page, total, perPage: 20, onPageChange: setPage })
    ),
    React.createElement(ConfirmModal, {
      open: !!confirm, danger: confirm?.action === 'delete',
      title: `${confirm?.action === 'delete' ? 'Delete' : confirm?.action === 'lock' ? 'Lock' : 'Unlock'} User`,
      message: `Are you sure you want to ${confirm?.action} user "${confirm?.name}"?`,
      onConfirm: () => handleAction(confirm.id, confirm.action), onCancel: () => setConfirm(null),
    })
  );
}

// ============ Model Management Page ============
function ModelManagementPage({ collectionName }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [editItem, setEditItem] = useState(null);
  const [editJson, setEditJson] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page, per_page: 20 });
    if (search) params.set('search', search);
    const data = await apiClient.get(`/models/${collectionName}?${params}`);
    setItems(data.items); setTotal(data.total);
  }, [page, search, collectionName]);

  useEffect(() => { load(); setPage(1); setSelectedIds(new Set()); }, [collectionName]);
  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    try {
      const parsed = JSON.parse(editJson);
      if (creating) {
        await apiClient.post(`/models/${collectionName}`, parsed);
      } else {
        await apiClient.put(`/models/${collectionName}/${editItem._id}`, parsed);
      }
      setEditItem(null); setCreating(false); load();
    } catch (err) { alert(err.message); }
  };

  const handleDelete = async (id) => {
    try {
      await apiClient.delete(`/models/${collectionName}/${id}`);
      setConfirm(null); load();
    } catch (err) { alert(err.message); }
  };

  const handleBulkDelete = async () => {
    try {
      await apiClient.post(`/models/${collectionName}/bulk-delete`, { ids: [...selectedIds] });
      setSelectedIds(new Set()); setConfirm(null); load();
    } catch (err) { alert(err.message); }
  };

  const toggleSelect = (id) => {
    const next = new Set(selectedIds);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelectedIds(next);
  };

  const displayName = collectionName.charAt(0).toUpperCase() + collectionName.slice(1);

  if (editItem || creating) {
    return React.createElement('div', { className: 'space-y-4' },
      React.createElement('button', { className: 'btn-secondary', onClick: () => { setEditItem(null); setCreating(false); } }, '← Back'),
      React.createElement('div', { className: 'card' },
        React.createElement('h2', { className: 'text-xl font-bold mb-4' }, creating ? `Create ${displayName} Item` : `Edit ${displayName} Item`),
        React.createElement('textarea', {
          className: 'input-field font-mono text-sm', rows: 20, value: editJson,
          onChange: e => setEditJson(e.target.value),
        }),
        React.createElement('button', { className: 'btn-primary mt-4', onClick: handleSave }, 'Save')
      )
    );
  }

  return React.createElement('div', { className: 'space-y-4' },
    React.createElement('div', { className: 'flex items-center justify-between' },
      React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, `${displayName} Management`),
      React.createElement('div', { className: 'flex gap-3' },
        React.createElement('input', { className: 'input-field w-64', placeholder: `Search ${collectionName}...`, value: search, onChange: e => { setSearch(e.target.value); setPage(1); } }),
        React.createElement('button', { className: 'btn-primary', onClick: () => { setCreating(true); setEditJson('{\n  "name": ""\n}'); } }, '+ Create'),
        selectedIds.size > 0 && React.createElement('button', { className: 'btn-danger', onClick: () => setConfirm({ action: 'bulk' }) }, `Delete (${selectedIds.size})`)
      )
    ),
    React.createElement('div', { className: 'card overflow-x-auto' },
      React.createElement('table', { className: 'w-full' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'border-b border-gray-100' },
            React.createElement('th', { className: 'table-header w-8' },
              React.createElement('input', { type: 'checkbox', onChange: e => setSelectedIds(e.target.checked ? new Set(items.map(i => i._id)) : new Set()) })
            ),
            ['ID', 'Name', 'Actions'].map(h => React.createElement('th', { key: h, className: 'table-header' }, h))
          )
        ),
        React.createElement('tbody', null,
          items.map(item => React.createElement('tr', { key: item._id, className: 'border-b border-gray-50 hover:bg-gray-50' },
            React.createElement('td', { className: 'table-cell' },
              React.createElement('input', { type: 'checkbox', checked: selectedIds.has(item._id), onChange: () => toggleSelect(item._id) })
            ),
            React.createElement('td', { className: 'table-cell font-mono text-xs' }, item._id?.substring(0, 8) + '...'),
            React.createElement('td', { className: 'table-cell font-medium' }, item.name || item.song_name || 'N/A'),
            React.createElement('td', { className: 'table-cell' },
              React.createElement('div', { className: 'flex gap-2' },
                React.createElement('button', { className: 'text-indigo-600 hover:underline text-sm', onClick: () => { setEditItem(item); setEditJson(JSON.stringify(item, null, 2)); } }, 'Edit'),
                React.createElement('button', { className: 'text-red-600 hover:underline text-sm', onClick: () => setConfirm({ action: 'delete', id: item._id, name: item.name }) }, 'Delete')
              )
            )
          ))
        )
      ),
      React.createElement(Pagination, { page, total, perPage: 20, onPageChange: setPage })
    ),
    React.createElement(ConfirmModal, {
      open: !!confirm, danger: true,
      title: confirm?.action === 'bulk' ? 'Bulk Delete' : 'Delete Item',
      message: confirm?.action === 'bulk' ? `Delete ${selectedIds.size} selected items?` : `Delete "${confirm?.name}"?`,
      onConfirm: () => confirm?.action === 'bulk' ? handleBulkDelete() : handleDelete(confirm.id),
      onCancel: () => setConfirm(null),
    })
  );
}

// ============ Logs Page ============
function LogsPage() {
  const [analytics, setAnalytics] = useState(null);
  const [errors, setErrors] = useState([]);
  const [errorsTotal, setErrorsTotal] = useState(0);
  const [errorsPage, setErrorsPage] = useState(1);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [tab, setTab] = useState('analytics');
  const [timeRange, setTimeRange] = useState('24h');
  const chartRef = useRef(null);
  const chartInstance = useRef(null);

  const getTimeRange = () => {
    const now = Math.floor(Date.now() / 1000);
    if (timeRange === '1h') return { start_time: now - 3600, end_time: now };
    if (timeRange === '24h') return { start_time: now - 86400, end_time: now };
    if (timeRange === '7d') return { start_time: now - 604800, end_time: now };
    return {};
  };

  useEffect(() => {
    const params = new URLSearchParams(getTimeRange());
    apiClient.get(`/logs/analytics?${params}`).then(setAnalytics).catch(() => {});
  }, [timeRange]);

  useEffect(() => {
    const params = new URLSearchParams({ ...getTimeRange(), page: errorsPage, per_page: 50 });
    apiClient.get(`/logs/errors?${params}`).then(d => { setErrors(d.items); setErrorsTotal(d.total); }).catch(() => {});
  }, [timeRange, errorsPage]);

  useEffect(() => {
    apiClient.get(`/logs/audit?page=${auditPage}&per_page=50`).then(d => { setAuditLogs(d.items); setAuditTotal(d.total); }).catch(() => {});
  }, [auditPage]);

  useEffect(() => {
    if (!analytics || !chartRef.current) return;
    if (chartInstance.current) chartInstance.current.destroy();
    const cats = analytics.categories || {};
    chartInstance.current = new Chart(chartRef.current, {
      type: 'bar',
      data: {
        labels: ['2xx', '3xx', '4xx', '5xx'],
        datasets: [{
          label: 'Request Count',
          data: [cats['2xx']?.count || 0, cats['3xx']?.count || 0, cats['4xx']?.count || 0, cats['5xx']?.count || 0],
          backgroundColor: ['#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
        }],
      },
      options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
    return () => { if (chartInstance.current) chartInstance.current.destroy(); };
  }, [analytics]);

  const tabs = ['analytics', 'errors', 'audit'];

  return React.createElement('div', { className: 'space-y-4' },
    React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Logs & Analytics'),
    React.createElement('div', { className: 'flex gap-2' },
      tabs.map(t => React.createElement('button', { key: t, className: `tab-btn ${tab === t ? 'active' : ''}`, onClick: () => setTab(t) }, t.charAt(0).toUpperCase() + t.slice(1)))
    ),
    tab === 'analytics' && React.createElement('div', { className: 'space-y-4' },
      React.createElement('div', { className: 'flex gap-2' },
        ['1h', '24h', '7d', '30d'].map(r => React.createElement('button', { key: r, className: `tab-btn ${timeRange === r ? 'active' : ''}`, onClick: () => setTimeRange(r) }, r))
      ),
      analytics && React.createElement('div', { className: 'grid grid-cols-1 md:grid-cols-4 gap-4' },
        React.createElement('div', { className: 'card text-center' },
          React.createElement('div', { className: 'text-2xl font-bold text-green-600' }, analytics.categories?.['2xx']?.count || 0),
          React.createElement('div', { className: 'text-sm text-gray-500' }, '2xx Success')
        ),
        React.createElement('div', { className: 'card text-center' },
          React.createElement('div', { className: 'text-2xl font-bold text-yellow-600' }, analytics.categories?.['3xx']?.count || 0),
          React.createElement('div', { className: 'text-sm text-gray-500' }, '3xx Redirect')
        ),
        React.createElement('div', { className: 'card text-center' },
          React.createElement('div', { className: 'text-2xl font-bold text-red-600' }, analytics.categories?.['4xx']?.count || 0),
          React.createElement('div', { className: 'text-sm text-gray-500' }, '4xx Client Error')
        ),
        React.createElement('div', { className: 'card text-center' },
          React.createElement('div', { className: 'text-2xl font-bold text-purple-600' }, analytics.categories?.['5xx']?.count || 0),
          React.createElement('div', { className: 'text-sm text-gray-500' }, '5xx Server Error')
        )
      ),
      React.createElement('div', { className: 'card' },
        React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Request Distribution'),
        React.createElement('canvas', { ref: chartRef, height: 100 })
      )
    ),
    tab === 'errors' && React.createElement('div', { className: 'card overflow-x-auto' },
      React.createElement('table', { className: 'w-full' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'border-b border-gray-100' },
            ['Time', 'Status', 'Method', 'Path', 'Duration', 'IP'].map(h => React.createElement('th', { key: h, className: 'table-header' }, h))
          )
        ),
        React.createElement('tbody', null,
          errors.map((e, i) => React.createElement('tr', { key: i, className: 'border-b border-gray-50' },
            React.createElement('td', { className: 'table-cell text-xs' }, new Date(e.timestamp * 1000).toLocaleString()),
            React.createElement('td', { className: 'table-cell' },
              React.createElement('span', { className: `badge ${e.status_code >= 500 ? 'badge-purple' : 'badge-red'}` }, e.status_code)
            ),
            React.createElement('td', { className: 'table-cell font-medium' }, e.method),
            React.createElement('td', { className: 'table-cell font-mono text-xs' }, e.path),
            React.createElement('td', { className: 'table-cell' }, `${e.process_time_ms?.toFixed(1)}ms`),
            React.createElement('td', { className: 'table-cell text-xs' }, e.client_ip)
          ))
        )
      ),
      React.createElement(Pagination, { page: errorsPage, total: errorsTotal, perPage: 50, onPageChange: setErrorsPage })
    ),
    tab === 'audit' && React.createElement('div', { className: 'card overflow-x-auto' },
      React.createElement('table', { className: 'w-full' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'border-b border-gray-100' },
            ['Time', 'Admin', 'Action', 'Target', 'IP'].map(h => React.createElement('th', { key: h, className: 'table-header' }, h))
          )
        ),
        React.createElement('tbody', null,
          auditLogs.map((l, i) => React.createElement('tr', { key: i, className: 'border-b border-gray-50' },
            React.createElement('td', { className: 'table-cell text-xs' }, new Date(l.timestamp * 1000).toLocaleString()),
            React.createElement('td', { className: 'table-cell font-medium' }, l.admin_username),
            React.createElement('td', { className: 'table-cell' }, React.createElement('span', { className: 'badge badge-blue' }, l.action)),
            React.createElement('td', { className: 'table-cell text-xs' }, `${l.target_type}${l.target_id ? ': ' + l.target_id.substring(0, 8) + '...' : ''}`),
            React.createElement('td', { className: 'table-cell text-xs' }, l.ip_address || 'N/A')
          ))
        )
      ),
      React.createElement(Pagination, { page: auditPage, total: auditTotal, perPage: 50, onPageChange: setAuditPage })
    )
  );
}

// ============ Redis Tools Page ============
function RedisToolsPage() {
  const [command, setCommand] = useState('');
  const [history, setHistory] = useState([]);
  const [info, setInfo] = useState(null);
  const [allowed, setAllowed] = useState([]);

  useEffect(() => {
    apiClient.get('/db/redis/info').then(setInfo).catch(() => {});
    apiClient.get('/db/redis/allowed-commands').then(d => setAllowed(d.allowed || [])).catch(() => {});
  }, []);

  const execute = async () => {
    if (!command.trim()) return;
    try {
      const result = await apiClient.post('/db/redis/execute', { command });
      setHistory(prev => [{ command, ...result, time: new Date().toLocaleTimeString() }, ...prev]);
      setCommand('');
    } catch (err) {
      setHistory(prev => [{ command, success: false, error: err.message, time: new Date().toLocaleTimeString() }, ...prev]);
    }
  };

  return React.createElement('div', { className: 'space-y-4' },
    React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Redis Tools'),
    info && React.createElement('div', { className: 'grid grid-cols-2 md:grid-cols-4 gap-4' },
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, info.connected ? '🟢' : '🔴'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, info.connected ? 'Connected' : 'Disconnected')
      ),
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, info.version || 'N/A'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, 'Version')
      ),
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, info.used_memory_human || 'N/A'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, 'Memory')
      ),
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, info.db_size ?? 'N/A'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, 'Keys')
      )
    ),
    React.createElement('div', { className: 'card' },
      React.createElement('h3', { className: 'text-lg font-semibold mb-3' }, 'Command Console'),
      React.createElement('div', { className: 'flex gap-2' },
        React.createElement('input', {
          className: 'input-field font-mono', placeholder: 'Enter Redis command (e.g., PING, KEYS *, GET key)',
          value: command, onChange: e => setCommand(e.target.value),
          onKeyDown: e => e.key === 'Enter' && execute(),
        }),
        React.createElement('button', { className: 'btn-primary', onClick: execute }, 'Execute')
      ),
      React.createElement('div', { className: 'mt-2 flex flex-wrap gap-1' },
        allowed.slice(0, 20).map(cmd => React.createElement('button', {
          key: cmd, className: 'text-xs bg-gray-100 px-2 py-1 rounded hover:bg-gray-200',
          onClick: () => setCommand(cmd.toUpperCase() + ' ')
        }, cmd))
      )
    ),
    React.createElement('div', { className: 'card' },
      React.createElement('h3', { className: 'text-lg font-semibold mb-3' }, 'Command History'),
      React.createElement('div', { className: 'space-y-2 max-h-96 overflow-y-auto' },
        history.map((h, i) => React.createElement('div', { key: i, className: `p-3 rounded-lg ${h.success ? 'bg-green-50' : 'bg-red-50'}` },
          React.createElement('div', { className: 'flex items-center justify-between' },
            React.createElement('code', { className: 'text-sm font-bold' }, `> ${h.command}`),
            React.createElement('span', { className: 'text-xs text-gray-400' }, h.time)
          ),
          React.createElement('pre', { className: 'text-sm mt-1 whitespace-pre-wrap' }, h.success ? h.result : `Error: ${h.error}`)
        ))
      )
    )
  );
}

// ============ MongoDB Tools Page ============
function MongoToolsPage() {
  const [collections, setCollections] = useState([]);
  const [selected, setSelected] = useState(null);
  const [docs, setDocs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    apiClient.get('/db/mongo/collections').then(setCollections).catch(() => {});
    apiClient.get('/db/mongo/stats').then(setStats).catch(() => {});
  }, []);

  const browse = useCallback(async (name, p = 1) => {
    setSelected(name); setPage(p);
    const data = await apiClient.get(`/db/mongo/collections/${name}?page=${p}&per_page=20`);
    setDocs(data.items); setTotal(data.total);
  }, []);

  const viewDoc = async (collName, docId) => {
    const doc = await apiClient.get(`/db/mongo/collections/${collName}/${docId}`);
    setSelectedDoc(doc);
  };

  if (selectedDoc) {
    return React.createElement('div', { className: 'space-y-4' },
      React.createElement('button', { className: 'btn-secondary', onClick: () => setSelectedDoc(null) }, '← Back'),
      React.createElement('div', { className: 'card' },
        React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Document Details'),
        React.createElement('pre', { className: 'bg-gray-50 p-4 rounded-lg text-sm overflow-x-auto font-mono' }, JSON.stringify(selectedDoc, null, 2))
      )
    );
  }

  if (selected) {
    return React.createElement('div', { className: 'space-y-4' },
      React.createElement('button', { className: 'btn-secondary', onClick: () => setSelected(null) }, '← Back to Collections'),
      React.createElement('h2', { className: 'text-xl font-bold' }, `Collection: ${selected}`),
      React.createElement('div', { className: 'card overflow-x-auto' },
        React.createElement('table', { className: 'w-full' },
          React.createElement('thead', null,
            React.createElement('tr', { className: 'border-b border-gray-100' },
              ['ID', 'Preview', 'Actions'].map(h => React.createElement('th', { key: h, className: 'table-header' }, h))
            )
          ),
          React.createElement('tbody', null,
            docs.map(d => React.createElement('tr', { key: d._id, className: 'border-b border-gray-50 hover:bg-gray-50' },
              React.createElement('td', { className: 'table-cell font-mono text-xs' }, String(d._id).substring(0, 12) + '...'),
              React.createElement('td', { className: 'table-cell text-xs max-w-md truncate' }, JSON.stringify(d).substring(0, 100) + '...'),
              React.createElement('td', { className: 'table-cell' },
                React.createElement('button', { className: 'text-indigo-600 hover:underline text-sm', onClick: () => viewDoc(selected, d._id) }, 'View')
              )
            ))
          )
        ),
        React.createElement(Pagination, { page, total, perPage: 20, onPageChange: p => browse(selected, p) })
      )
    );
  }

  return React.createElement('div', { className: 'space-y-4' },
    React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, 'MongoDB Tools'),
    stats && React.createElement('div', { className: 'grid grid-cols-2 md:grid-cols-4 gap-4' },
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, stats.connected ? '🟢' : '🔴'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, stats.connected ? 'Connected' : 'Disconnected')
      ),
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, stats.collections ?? 'N/A'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, 'Collections')
      ),
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, stats.objects ?? 'N/A'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, 'Documents')
      ),
      React.createElement('div', { className: 'card text-center' },
        React.createElement('div', { className: 'text-lg font-bold' }, stats.indexes ?? 'N/A'),
        React.createElement('div', { className: 'text-sm text-gray-500' }, 'Indexes')
      )
    ),
    React.createElement('div', { className: 'card' },
      React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Collections'),
      React.createElement('div', { className: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3' },
        collections.map(c => React.createElement('button', {
          key: c.name, className: 'p-4 bg-gray-50 rounded-lg hover:bg-indigo-50 text-left transition-colors',
          onClick: () => browse(c.name),
        },
          React.createElement('div', { className: 'font-medium' }, c.name),
          React.createElement('div', { className: 'text-sm text-gray-500' }, `${c.document_count} documents`)
        ))
      )
    )
  );
}

// ============ System Page ============
function SystemPage() {
  const { isSuperAdmin } = useAuth();
  const [health, setHealth] = useState(null);
  const [restartConfirm, setRestartConfirm] = useState(false);
  const [dashboard, setDashboard] = useState(null);

  useEffect(() => {
    apiClient.get('/system/health').then(setHealth).catch(() => {});
    apiClient.get('/system/dashboard').then(setDashboard).catch(() => {});
  }, []);

  const handleRestart = async () => {
    try {
      await apiClient.post('/system/restart');
      setRestartConfirm(false);
      alert('Restart initiated');
    } catch (err) { alert(err.message); setRestartConfirm(false); }
  };

  return React.createElement('div', { className: 'space-y-4' },
    React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, 'System Controls'),
    health && React.createElement('div', { className: 'card' },
      React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Health Checks'),
      React.createElement('div', { className: `inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium mb-4 ${health.status === 'healthy' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}` },
        health.status === 'healthy' ? '✅' : '⚠️', health.status
      ),
      React.createElement('div', { className: 'space-y-2' },
        Object.entries(health.checks || {}).map(([name, check]) =>
          React.createElement('div', { key: name, className: 'flex items-center justify-between p-3 bg-gray-50 rounded-lg' },
            React.createElement('span', { className: 'font-medium capitalize' }, name),
            React.createElement('div', { className: 'flex items-center gap-3' },
              check.latency_ms !== undefined && React.createElement('span', { className: 'text-xs text-gray-500' }, `${check.latency_ms}ms`),
              React.createElement('span', { className: `badge ${check.status === 'healthy' ? 'badge-green' : 'badge-red'}` }, check.status)
            )
          )
        )
      )
    ),
    dashboard && React.createElement('div', { className: 'card' },
      React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'System Info'),
      React.createElement('div', { className: 'grid grid-cols-2 gap-4' },
        React.createElement('div', { className: 'p-3 bg-gray-50 rounded-lg' },
          React.createElement('div', { className: 'text-xs text-gray-500' }, 'PID'),
          React.createElement('div', { className: 'font-medium' }, dashboard.system?.pid)
        ),
        React.createElement('div', { className: 'p-3 bg-gray-50 rounded-lg' },
          React.createElement('div', { className: 'text-xs text-gray-500' }, 'Python'),
          React.createElement('div', { className: 'font-medium text-xs' }, dashboard.system?.python_version?.split(' ')[0])
        ),
        React.createElement('div', { className: 'p-3 bg-gray-50 rounded-lg' },
          React.createElement('div', { className: 'text-xs text-gray-500' }, 'CPU'),
          React.createElement('div', { className: 'font-medium' }, `${dashboard.system?.cpu_percent}%`)
        ),
        React.createElement('div', { className: 'p-3 bg-gray-50 rounded-lg' },
          React.createElement('div', { className: 'text-xs text-gray-500' }, 'Restart Enabled'),
          React.createElement('div', { className: 'font-medium' }, dashboard.restart_enabled ? 'Yes' : 'No')
        )
      )
    ),
    isSuperAdmin && React.createElement('div', { className: 'card' },
      React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Server Controls'),
      React.createElement('p', { className: 'text-sm text-gray-500 mb-4' }, 'Super admin only: Restart the server process. Use with caution.'),
      React.createElement('button', { className: 'btn-danger', onClick: () => setRestartConfirm(true) }, '🔄 Restart Server')
    ),
    React.createElement(ConfirmModal, {
      open: restartConfirm, danger: true,
      title: 'Restart Server',
      message: 'Are you sure you want to restart the server? This will briefly interrupt all connections.',
      onConfirm: handleRestart, onCancel: () => setRestartConfirm(false),
    })
  );
}

// ============ Admin Management Page ============
function AdminManagementPage() {
  const [admins, setAdmins] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(async () => {
    const data = await apiClient.get(`/admins/?page=${page}&per_page=20`);
    setAdmins(data.items); setTotal(data.total);
  }, [page]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      await apiClient.post('/admins/', { username: newUsername, password: newPassword });
      setCreating(false); setNewUsername(''); setNewPassword(''); load();
    } catch (err) { alert(err.message); }
  };

  const handleDelete = async (id) => {
    try {
      await apiClient.delete(`/admins/${id}`);
      setConfirm(null); load();
    } catch (err) { alert(err.message); }
  };

  const handleToggleActive = async (id, currentActive) => {
    try {
      await apiClient.patch(`/admins/${id}`, { is_active: !currentActive });
      load();
    } catch (err) { alert(err.message); }
  };

  return React.createElement('div', { className: 'space-y-4' },
    React.createElement('div', { className: 'flex items-center justify-between' },
      React.createElement('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Admin Management'),
      React.createElement('button', { className: 'btn-primary', onClick: () => setCreating(true) }, '+ Create Admin')
    ),
    creating && React.createElement('div', { className: 'card' },
      React.createElement('h3', { className: 'text-lg font-semibold mb-4' }, 'Create New Admin'),
      React.createElement('div', { className: 'space-y-3 max-w-md' },
        React.createElement('input', { className: 'input-field', placeholder: 'Username', value: newUsername, onChange: e => setNewUsername(e.target.value) }),
        React.createElement('input', { className: 'input-field', type: 'password', placeholder: 'Password (min 8 chars)', value: newPassword, onChange: e => setNewPassword(e.target.value) }),
        React.createElement('div', { className: 'flex gap-2' },
          React.createElement('button', { className: 'btn-primary', onClick: handleCreate }, 'Create'),
          React.createElement('button', { className: 'btn-secondary', onClick: () => setCreating(false) }, 'Cancel')
        )
      )
    ),
    React.createElement('div', { className: 'card overflow-x-auto' },
      React.createElement('table', { className: 'w-full' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'border-b border-gray-100' },
            ['Username', 'Role', 'Active', 'Created', 'Last Login', 'Actions'].map(h =>
              React.createElement('th', { key: h, className: 'table-header' }, h))
          )
        ),
        React.createElement('tbody', null,
          admins.map(a => React.createElement('tr', { key: a._id, className: 'border-b border-gray-50 hover:bg-gray-50' },
            React.createElement('td', { className: 'table-cell font-medium' }, a.username),
            React.createElement('td', { className: 'table-cell' },
              React.createElement('span', { className: `badge ${a.role === 'super_admin' ? 'badge-purple' : 'badge-blue'}` }, a.role)
            ),
            React.createElement('td', { className: 'table-cell' },
              React.createElement('span', { className: `badge ${a.is_active ? 'badge-green' : 'badge-red'}` }, a.is_active ? 'Active' : 'Disabled')
            ),
            React.createElement('td', { className: 'table-cell text-xs' }, a.created_at_timestamp ? new Date(a.created_at_timestamp * 1000).toLocaleDateString() : 'N/A'),
            React.createElement('td', { className: 'table-cell text-xs' }, a.last_login_timestamp ? new Date(a.last_login_timestamp * 1000).toLocaleString() : 'Never'),
            React.createElement('td', { className: 'table-cell' },
              a.role !== 'super_admin' ? React.createElement('div', { className: 'flex gap-2' },
                React.createElement('button', { className: 'text-indigo-600 hover:underline text-sm', onClick: () => handleToggleActive(a._id, a.is_active) }, a.is_active ? 'Disable' : 'Enable'),
                React.createElement('button', { className: 'text-red-600 hover:underline text-sm', onClick: () => setConfirm({ id: a._id, name: a.username }) }, 'Delete')
              ) : React.createElement('span', { className: 'text-xs text-gray-400' }, 'Protected')
            )
          ))
        )
      ),
      React.createElement(Pagination, { page, total, perPage: 20, onPageChange: setPage })
    ),
    React.createElement(ConfirmModal, {
      open: !!confirm, danger: true,
      title: 'Delete Admin', message: `Are you sure you want to delete admin "${confirm?.name}"?`,
      onConfirm: () => handleDelete(confirm.id), onCancel: () => setConfirm(null),
    })
  );
}

// ============ App Root ============
function App() {
  const path = useHashRouter();
  const { user } = useAuth();

  if (!user || path === '/login') return React.createElement(LoginPage);

  let content;
  if (path === '/dashboard') content = React.createElement(DashboardPage);
  else if (path === '/users') content = React.createElement(UsersPage);
  else if (path.startsWith('/models/')) content = React.createElement(ModelManagementPage, { collectionName: path.split('/')[2] });
  else if (path === '/logs') content = React.createElement(LogsPage);
  else if (path === '/db/redis') content = React.createElement(RedisToolsPage);
  else if (path === '/db/mongo') content = React.createElement(MongoToolsPage);
  else if (path === '/system') content = React.createElement(SystemPage);
  else if (path === '/admins') content = React.createElement(AdminManagementPage);
  else content = React.createElement(DashboardPage);

  return React.createElement('div', { className: 'flex min-h-screen' },
    React.createElement(Sidebar, { currentPath: path }),
    React.createElement('main', { className: 'flex-1 p-8 overflow-y-auto' }, content)
  );
}

function Root() {
  return React.createElement(AuthProvider, null, React.createElement(App));
}

ReactDOM.createRoot(document.getElementById('admin-root')).render(React.createElement(Root));
</script>
</body>
</html>"""
