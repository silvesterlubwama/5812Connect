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
