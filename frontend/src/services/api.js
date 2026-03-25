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
  visitorRegister: (data) => api.post('/auth/visitor-register', data),
  me: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),
  resetPassword: (token, new_password) => api.post('/auth/reset-password', { token, new_password }),
};

// ---- MEMBERS ----
export const membersApi = {
  list: (params) => api.get('/members', { params }),
  get: (id) => api.get(`/members/${id}`),
  create: (data) => api.post('/members', data),
  update: (id, data) => api.put(`/members/${id}`, data),
  delete: (id) => api.delete(`/members/${id}`),
  documents: (id) => api.get(`/members/${id}/documents`),
  latestIdScan: (id) => api.get(`/members/${id}/documents/id-scan`),
  uploadDocument: (id, formData) => api.post(`/members/${id}/documents`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  downloadDocument: (docId) => api.get(`/documents/${docId}/download`, { responseType: 'blob' }),
  archiveDocument: (docId) => api.put(`/documents/${docId}/archive`),
};

// ---- EVENTS ----
export const eventsApi = {
  list: (params) => api.get('/events', { params }),
  get: (id) => api.get(`/events/${id}`),
  create: (data) => api.post('/events', data),
  update: (id, data) => api.put(`/events/${id}`, data),
  delete: (id) => api.delete(`/events/${id}`),
  duplicate: (id) => api.post(`/events/${id}/duplicate`),
  types: () => api.get('/event-types'),
  createType: (data) => api.post('/event-types', data),
  updateType: (id, data) => api.put(`/event-types/${id}`, data),
  deleteType: (id) => api.delete(`/event-types/${id}`),
};

// ---- TASKS ----
export const tasksApi = {
  list: (params) => api.get('/tasks', { params }),
  create: (data) => api.post('/tasks', data),
  update: (id, data) => api.put(`/tasks/${id}`, data),
  delete: (id) => api.delete(`/tasks/${id}`),
  importTrello: (data) => api.post('/tasks/import-trello', data),
};

// ---- CHECK-INS ----
export const checkinsApi = {
  list: (params) => api.get('/checkins', { params }),
  create: (data) => api.post('/checkins', data),
  stats: () => api.get('/checkins/stats'),
  pinCheckin: (data) => api.post('/checkins/pin', data),
  checkout: (id) => api.post(`/checkins/${id}/checkout`),
};

// ---- VENUES ----
export const venuesApi = {
  list: (params) => api.get('/venues', { params }),
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
  pinCheckin: (data) => api.post('/kiosk/pin-checkin', data),
};

// ---- FINANCIAL ----
export const financialApi = {
  summary: (location_id) => api.get('/financial/summary', { params: location_id ? { location_id } : {} }),
  donations: (params) => api.get('/financial/donations', { params }),
  createDonation: (data) => api.post('/financial/donations', data),
  expenses: (params) => api.get('/financial/expenses', { params }),
  createExpense: (data) => api.post('/financial/expenses', data),
  distributeFunds: (data) => api.post('/financial/distribute-funds', data),
  pendingExpenses: () => api.get('/financial/expenses/pending'),
  approveExpense: (id, comment) => api.put(`/financial/expenses/${id}/approve`, { comment }),
  rejectExpense: (id, comment) => api.put(`/financial/expenses/${id}/reject`, { comment }),
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
  get: (id) => api.get(`/families/${id}`),
  create: (data) => api.post('/families', data),
  update: (id, data) => api.put(`/families/${id}`, data),
  delete: (id) => api.delete(`/families/${id}`),
  addGuardian: (familyId, data) => api.post(`/families/${familyId}/guardians`, data),
  updateGuardian: (familyId, guardianId, data) => api.put(`/families/${familyId}/guardians/${guardianId}`, data),
  removeGuardian: (familyId, guardianId) => api.delete(`/families/${familyId}/guardians/${guardianId}`),
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
  getStaff: (id) => api.get(`/locations/${id}/staff`),
  assignStaff: (id, staff_ids) => api.put(`/locations/${id}/assign-staff`, { staff_ids }),
  setDirector: (id, director_id) => api.put(`/locations/${id}/director`, { director_id }),
};

export const exchangeApi = {
  getRate: (from, to) => api.get('/exchange-rate', { params: { from_currency: from, to_currency: to } }),
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
  list: (params) => api.get('/admin/audit', { params }),
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
  getProgram: (id) => api.get(`/outreach/programs/${id}`),
  createProgram: (data) => api.post('/outreach/programs', data),
  updateProgram: (id, data) => api.put(`/outreach/programs/${id}`, data),
  deleteProgram: (id) => api.delete(`/outreach/programs/${id}`),
  duplicateProgram: (id) => api.post(`/outreach/programs/${id}/duplicate`),
  generateEvents: (id, data) => api.post(`/outreach/programs/${id}/generate-events`, data),
  sessions: (params) => api.get('/outreach/sessions', { params }),
  createSession: (data) => api.post('/outreach/sessions', data),
  categories: () => api.get('/programme-categories'),
  createCategory: (data) => api.post('/programme-categories', data),
  updateCategory: (id, data) => api.put(`/programme-categories/${id}`, data),
  deleteCategory: (id) => api.delete(`/programme-categories/${id}`),
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
  types: () => api.get('/resource-types'),
  createType: (data) => api.post('/resource-types', data),
  updateType: (id, data) => api.put(`/resource-types/${id}`, data),
  deleteType: (id) => api.delete(`/resource-types/${id}`),
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

export const importApi = {
  childrenParents: (rows) => api.post('/import/children-parents', { rows }),
  staff: (rows) => api.post('/import/staff', { rows }),
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

export const chatApi = {
  conversations: () => api.get('/chat/conversations'),
  createConversation: (data) => api.post('/chat/conversations', data),
  messages: (convId, params) => api.get(`/chat/conversations/${convId}/messages`, { params }),
  sendMessage: (convId, text) => api.post(`/chat/conversations/${convId}/messages`, { text }),
  aiAssistant: (message, session_id) => api.post('/chat/ai-assistant', { message, session_id }),
};

export const bookingsApi = {
  list: (params) => api.get('/bookings', { params }),
  create: (data) => api.post('/bookings', data),
  update: (id, data) => api.put(`/bookings/${id}`, data),
  cancel: (id) => api.delete(`/bookings/${id}`),
};

// ---- ACCESS CONTROL ----
export const accessApi = {
  residents: (params) => api.get('/access/residents', { params }),
  assignResident: (data) => api.post('/access/residents', data),
  removeResident: (id) => api.delete(`/access/residents/${id}`),
  staffPasses: (params) => api.get('/access/staff-passes', { params }),
  assignStaffPass: (data) => api.post('/access/staff-passes', data),
  revokeStaffPass: (id) => api.delete(`/access/staff-passes/${id}`),
  guestRequests: (params) => api.get('/access/guest-requests', { params }),
  requestGuestVisit: (data) => api.post('/access/guest-requests', data),
  approveGuest: (id) => api.put(`/access/guest-requests/${id}/approve`),
  rejectGuest: (id) => api.put(`/access/guest-requests/${id}/reject`),
  scan: (data) => api.post('/access/scan', data),
  scanLog: (params) => api.get('/access/scan-log', { params }),
};

// ---- REPORTS ----
export const reportsApi = {
  summary: (params) => api.get('/reports/summary', { params }),
  downloadPdf: (params) => api.get('/reports/pdf', { params, responseType: 'blob' }),
};

// ---- CSV FILE UPLOAD ----
export const csvUploadApi = {
  uploadMembers: (formData) => api.post('/import/csv/members', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  uploadChildrenParents: (formData) => api.post('/import/csv/children-parents', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  uploadStaff: (formData) => api.post('/import/csv/staff', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
};

// ---- PUSH NOTIFICATIONS ----
export const pushApi = {
  vapidKey: () => api.get('/push/vapid-key'),
  subscribe: (subscription) => api.post('/push/subscribe', { subscription }),
  unsubscribe: () => api.delete('/push/subscribe'),
};

// ---- OFFLINE SYNC ----
export const syncApi = {
  messages: (messages) => api.post('/sync/messages', { messages }),
};

// ---- BOARDS (Kanban) ----
export const boardsApi = {
  list: () => api.get('/boards'),
  get: (id) => api.get(`/boards/${id}`),
  create: (data) => api.post('/boards', data),
  update: (id, data) => api.put(`/boards/${id}`, data),
  delete: (id) => api.delete(`/boards/${id}`),
  // Lists
  addList: (boardId, data) => api.post(`/boards/${boardId}/lists`, data),
  updateList: (boardId, listId, data) => api.put(`/boards/${boardId}/lists/${listId}`, data),
  deleteList: (boardId, listId) => api.delete(`/boards/${boardId}/lists/${listId}`),
  archiveList: (boardId, listId) => api.post(`/boards/${boardId}/lists/${listId}/archive`),
  restoreList: (boardId, listId) => api.post(`/boards/${boardId}/lists/${listId}/restore`),
  archivedLists: (boardId) => api.get(`/boards/${boardId}/lists/archived`),
  reorderLists: (boardId, listIds) => api.post(`/boards/${boardId}/lists/reorder`, { list_ids: listIds }),
  // Trello import
  importTrello: (data) => api.post('/boards/import-trello', data),
  // Tasks (filtered)
  tasks: (boardId, listId) => api.get('/tasks', { params: { board_id: boardId, list_id: listId } }),
  moveTask: (taskId, data) => api.patch(`/tasks/${taskId}/move`, data),
};

// ---- TASKS EXTENDED ----
export const tasksExtApi = {
  archive: (id) => api.post(`/tasks/${id}/archive`),
  restore: (id) => api.post(`/tasks/${id}/restore`),
  archived: (boardId) => api.get('/tasks/archived', { params: { board_id: boardId } }),
  uploadAttachment: (taskId, formData) => api.post(`/tasks/${taskId}/attachments`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  deleteAttachment: (taskId, attId) => api.delete(`/tasks/${taskId}/attachments/${attId}`),
};
export const biometricApi = {
  register: (data) => api.post('/biometric/register', data),
  verify: (data) => api.post('/biometric/verify', data),
};

export const nfcApi = {
  register: (data) => api.post('/nfc/register', data),
  scan: (data) => api.post('/nfc/scan', data),
};

// ---- WEBAUTHN (Passkey/FIDO2) ----
export const webAuthnApi = {
  registerBegin: (body = {}) => api.post('/webauthn/register/begin', body),
  registerComplete: (data) => api.post('/webauthn/register/complete', data),
  authenticateBegin: (email, rpId = '') => api.post('/webauthn/authenticate/begin', { email, rpId }),
  authenticateComplete: (data) => api.post('/webauthn/authenticate/complete', data),
  listCredentials: () => api.get('/webauthn/credentials'),
  removeCredential: (id) => api.delete(`/webauthn/credentials/${id}`),
};

// ---- PORTAL (SELF-SERVICE) ----
export const portalApi = {
  dashboard: () => api.get('/portal/dashboard'),
  profile: () => api.get('/portal/profile'),
  updateProfile: (data) => api.put('/portal/profile', data),
  tasks: (params) => api.get('/portal/tasks', { params }),
  updateTaskStatus: (id, status) => api.put(`/portal/tasks/${id}/status`, { status }),
  expenses: () => api.get('/portal/expenses'),
  createExpense: (data) => api.post('/portal/expenses', data),
  cashRequest: (data) => api.post('/portal/cash-request', data),
  events: () => api.get('/portal/events'),
  rsvpEvent: (id) => api.post(`/portal/events/${id}/rsvp`),
  checkins: () => api.get('/portal/checkins'),
  documents: () => api.get('/portal/documents'),
  sales: () => api.get('/portal/sales'),
  family: () => api.get('/portal/family'),
  updateFamily: (data) => api.put('/portal/family', data),
  addChild: (data) => api.post('/portal/family/children', data),
  addGuardian: (data) => api.post('/portal/family/guardians', data),
};

// ---- ADMIN ----
export const adminApi = {
  users: (params) => api.get('/admin/users', { params }),
  getUser: (id) => api.get(`/admin/users/${id}`),
  getUserFullProfile: (id) => api.get(`/admin/users/${id}/profile`),
  createUser: (data) => api.post('/admin/users', data),
  importUsers: (users) => api.post('/admin/users/import', { users }),
  updateUser: (id, data) => api.put(`/admin/users/${id}`, data),
  resetPassword: (id, new_password) => api.post(`/admin/users/${id}/reset-password`, { new_password }),
  deleteUser: (id) => api.delete(`/admin/users/${id}`),
  bulkUpdateUsers: (user_ids, updates) => api.post('/admin/users/bulk-update', { user_ids, updates }),
  bulkDeleteUsers: (user_ids) => api.post('/admin/users/bulk-delete', { user_ids }),
  bulkUpdateMembers: (member_ids, updates) => api.post('/admin/members/bulk-update', { member_ids, updates }),
  bulkDeleteMembers: (member_ids) => api.post('/admin/members/bulk-delete', { member_ids }),
  audit: (params) => api.get('/admin/audit', { params }),
  deletedItems: (collection) => api.get('/admin/deleted-items', { params: collection ? { collection } : {} }),
  restoreItem: (id) => api.post(`/admin/deleted-items/${id}/restore`),
  permanentDelete: (id) => api.delete(`/admin/deleted-items/${id}`),
};

// ---- DOCUMENTS ----
export const documentsApi = {
  idTypes: () => api.get('/documents/id-types'),
  list: (memberId) => api.get(`/members/${memberId}/documents`),
  upload: (memberId, formData) => api.post(`/members/${memberId}/documents`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  fileUrl: (docId) => `${BACKEND_URL}/api/documents/${docId}/file`,
  delete: (docId) => api.delete(`/documents/${docId}`),
  // Requests
  listRequests: (params) => api.get('/document-requests', { params }),
  createRequest: (data) => api.post('/document-requests', data),
  cancelRequest: (id) => api.delete(`/document-requests/${id}`),
};

// ---- LOCATION VENUES (Event Location Picker) ----
export const locationVenuesApi = {
  get: (locationId) => api.get(`/locations/${locationId}/venues`),
};
