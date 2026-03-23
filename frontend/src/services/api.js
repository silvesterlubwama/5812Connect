import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const api = axios.create({ baseURL: `${BACKEND_URL}/api` });

// Attach token to every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('5812_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Handle 401
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('5812_token');
      localStorage.removeItem('5812_auth_user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default api;

// ---- AUTH ----
export const authApi = {
  login: (identifier, password) => api.post('/auth/login', { identifier, password }),
  register: (data) => api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
};

// ---- MEMBERS ----
export const membersApi = {
  list: (params) => api.get('/members', { params }),
  get: (id) => api.get(`/members/${id}`),
  create: (data) => api.post('/members', data),
  update: (id, data) => api.put(`/members/${id}`, data),
  delete: (id) => api.delete(`/members/${id}`),
};

// ---- EVENTS ----
export const eventsApi = {
  list: (params) => api.get('/events', { params }),
  get: (id) => api.get(`/events/${id}`),
  create: (data) => api.post('/events', data),
  update: (id, data) => api.put(`/events/${id}`, data),
  delete: (id) => api.delete(`/events/${id}`),
};

// ---- TASKS ----
export const tasksApi = {
  list: (params) => api.get('/tasks', { params }),
  create: (data) => api.post('/tasks', data),
  update: (id, data) => api.put(`/tasks/${id}`, data),
  delete: (id) => api.delete(`/tasks/${id}`),
};

// ---- CHECK-INS ----
export const checkinsApi = {
  list: (params) => api.get('/checkins', { params }),
  create: (data) => api.post('/checkins', data),
  stats: () => api.get('/checkins/stats'),
};

// ---- VENUES ----
export const venuesApi = {
  list: () => api.get('/venues'),
  create: (data) => api.post('/venues', data),
  update: (id, data) => api.put(`/venues/${id}`, data),
  delete: (id) => api.delete(`/venues/${id}`),
};

// ---- DASHBOARD ----
export const dashboardApi = {
  stats: () => api.get('/dashboard/stats'),
};

// ---- PUBLIC ----
export const publicApi = {
  events: () => api.get('/public/events'),
  venues: () => api.get('/public/venues'),
  bookEvent: (data) => api.post('/public/bookings/event', data),
  bookSpace: (data) => api.post('/public/bookings/space', data),
  checkStatus: (params) => api.get('/public/bookings/status', { params }),
};

// ---- KIOSK ----
export const kioskApi = {
  checkin: (data) => api.post('/kiosk/checkin', data),
  lookup: (identifier) => api.get('/kiosk/lookup', { params: { identifier } }),
};

// ---- FINANCIAL ----
export const financialApi = {
  summary: () => api.get('/financial/summary'),
  donations: (params) => api.get('/financial/donations', { params }),
  createDonation: (data) => api.post('/financial/donations', data),
  expenses: (params) => api.get('/financial/expenses', { params }),
  createExpense: (data) => api.post('/financial/expenses', data),
};

// ---- PRODUCTS & SALES ----
export const productsApi = {
  list: () => api.get('/products'),
  create: (data) => api.post('/products', data),
  update: (id, data) => api.put(`/products/${id}`, data),
  delete: (id) => api.delete(`/products/${id}`),
};
export const salesApi = {
  list: (params) => api.get('/sales', { params }),
  create: (data) => api.post('/sales', data),
};

// ---- FAMILIES ----
export const familiesApi = {
  list: (params) => api.get('/families', { params }),
  create: (data) => api.post('/families', data),
  update: (id, data) => api.put(`/families/${id}`, data),
  delete: (id) => api.delete(`/families/${id}`),
};
export const childrenApi = {
  list: (params) => api.get('/children', { params }),
  create: (data) => api.post('/children', data),
  update: (id, data) => api.put(`/children/${id}`, data),
  delete: (id) => api.delete(`/children/${id}`),
};
export const guestsApi = {
  list: (params) => api.get('/guests', { params }),
  create: (data) => api.post('/guests', data),
  delete: (id) => api.delete(`/guests/${id}`),
};

// ---- LOCATIONS ----
export const locationsApi = {
  list: () => api.get('/locations'),
  create: (data) => api.post('/locations', data),
  update: (id, data) => api.put(`/locations/${id}`, data),
  delete: (id) => api.delete(`/locations/${id}`),
};

// ---- NOTIFICATIONS ----
export const notificationsApi = {
  list: () => api.get('/notifications'),
  unreadCount: () => api.get('/notifications/unread-count'),
  create: (data) => api.post('/notifications', data),
  markRead: (id) => api.put(`/notifications/${id}/read`),
  markAllRead: () => api.put('/notifications/read-all'),
  delete: (id) => api.delete(`/notifications/${id}`),
};

// ---- SEARCH ----
export const searchApi = {
  query: (q) => api.get('/search', { params: { q } }),
};

// ---- AUDIT ----
export const auditApi = {
  list: (params) => api.get('/audit', { params }),
};

// ---- PEOPLE STATS ----
export const peopleApi = {
  stats: () => api.get('/people/stats'),
};

// ---- EXPORT ----
export const exportApi = {
  members: () => `${BACKEND_URL}/api/export/members`,
  financial: () => `${BACKEND_URL}/api/export/financial`,
  events: () => `${BACKEND_URL}/api/export/events`,
  ical: () => `${BACKEND_URL}/api/export/events.ics`,
};

// ---- OUTREACH ----
export const outreachApi = {
  programs: (params) => api.get('/outreach/programs', { params }),
  createProgram: (data) => api.post('/outreach/programs', data),
  updateProgram: (id, data) => api.put(`/outreach/programs/${id}`, data),
  deleteProgram: (id) => api.delete(`/outreach/programs/${id}`),
  sessions: (params) => api.get('/outreach/sessions', { params }),
  createSession: (data) => api.post('/outreach/sessions', data),
};

// ---- RESOURCES ----
export const resourcesApi = {
  list: () => api.get('/resources'),
  create: (data) => api.post('/resources', data),
  update: (id, data) => api.put(`/resources/${id}`, data),
  delete: (id) => api.delete(`/resources/${id}`),
  bookings: (params) => api.get('/resources/bookings', { params }),
  createBooking: (data) => api.post('/resources/bookings', data),
  deleteBooking: (id) => api.delete(`/resources/bookings/${id}`),
};

// ---- ANNOUNCEMENTS ----
export const announcementsApi = {
  list: () => api.get('/announcements'),
  create: (data) => api.post('/announcements', data),
  delete: (id) => api.delete(`/announcements/${id}`),
  togglePin: (id) => api.put(`/announcements/${id}/pin`),
};

// ---- BADGES ----
export const badgesApi = {
  list: () => api.get('/badges'),
  create: (data) => api.post('/badges', data),
  delete: (id) => api.delete(`/badges/${id}`),
  issueTo: (memberId, badgeId) => api.post(`/members/${memberId}/issue-badge?badge_id=${badgeId}`),
  memberBadges: (memberId) => api.get(`/members/${memberId}/badges`),
};

// ---- MEMBER APPROVALS ----
export const approvalsApi = {
  pending: () => api.get('/members/pending'),
  approve: (id) => api.put(`/members/${id}/approve`),
  reject: (id) => api.put(`/members/${id}/reject`),
  bulkImport: (data) => api.post('/members/bulk-import', { members_data: data }),
};

// ---- ANALYTICS ----
export const analyticsApi = {
  attendance: () => api.get('/analytics/attendance'),
  sales: () => api.get('/analytics/sales'),
  locations: () => api.get('/analytics/locations'),
};

// ---- FINANCIAL EXTRAS ----
export const financialExtrasApi = {
  cashflow: (months) => api.get('/financial/cashflow', { params: { months } }),
  getBalance: () => api.get('/financial/balance'),
  setBalance: (opening_balance) => api.put('/financial/balance', null, { params: { opening_balance } }),
};

// ---- PARENT ----
export const parentApi = {
  children: () => api.get('/parent/children'),
  dashboard: () => api.get('/parent/dashboard'),
};

// ---- APP SETTINGS ----
export const appSettingsApi = {
  get: () => api.get('/app-settings'),
  update: (data) => api.put('/app-settings', data),
};
