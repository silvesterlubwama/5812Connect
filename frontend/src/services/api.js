import axios from 'axios';
import { secureStorage } from './secureStorage';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const api = axios.create({ baseURL: `${BACKEND_URL}/api` });

api.interceptors.request.use(config => {
  const token = secureStorage.getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Handle 401
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      secureStorage.removeToken();
      secureStorage.removeUser();
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default api;

// ---- AUTH ----
export const authApi = {
  login: (identifier, password, totp_code) => api.post('/auth/login', { identifier, password, totp_code }),
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
  bulkExport: (ids) => api.post('/members/bulk-export', { ids }),
};

// ---- EVENTS ----
export const eventsApi = {
  list: (params) => api.get('/events', { params }),
  get: (id) => api.get(`/events/${id}`),
  create: (data) => api.post('/events', data),
  update: (id, data) => api.put(`/events/${id}`, data),
  delete: (id) => api.delete(`/events/${id}`),
  share: (id, userIds) => api.put(`/events/${id}/share`, { user_ids: userIds }),
  duplicate: (id) => api.post(`/events/${id}/duplicate`),
  types: () => api.get('/event-types'),
  createType: (data) => api.post('/event-types', data),
  updateType: (id, data) => api.put(`/event-types/${id}`, data),
  deleteType: (id) => api.delete(`/event-types/${id}`),
  exportIcal: () => api.get('/events/export/ical', { responseType: 'blob' }),
  importIcal: (data) => api.post('/events/import/ical', data),
  bulkUpdate: (ids, updates) => api.put('/events/bulk-update', { ids, updates }),
  bulkDelete: (ids) => api.post('/events/bulk-delete', { ids }),
  bulkExport: (ids) => api.post('/events/bulk-export', { ids }),
};

// ---- TASKS ----
export const tasksApi = {
  list: (params) => api.get('/tasks', { params }),
  create: (data) => api.post('/tasks', data),
  update: (id, data) => api.put(`/tasks/${id}`, data),
  delete: (id) => api.delete(`/tasks/${id}`),
  importTrello: (data) => api.post('/tasks/import-trello', data),
  bulkUpdate: (ids, updates) => api.put('/tasks/bulk-update', { ids, updates }),
  bulkDelete: (ids) => api.post('/tasks/bulk-delete', { ids }),
  bulkArchive: (ids, archive) => api.post('/tasks/bulk-archive', { ids, archive }),
};

// ---- CHECK-INS ----
export const checkinsApi = {
  list: (params) => api.get('/checkins', { params }),
  create: (data) => api.post('/checkins', data),
  stats: () => api.get('/checkins/stats'),
  pinCheckin: (data) => api.post('/checkins/pin', data),
  checkout: (id) => api.post(`/checkins/${id}/checkout`),
  parentLookup: (data) => api.post('/checkins/parent-lookup', data),
  qrScan: (data) => api.post('/checkins/qr-scan', data),
};

// ---- VENUES ----
export const venuesApi = {
  list: (params) => api.get('/venues', { params }),
  create: (data) => api.post('/venues', data),
  update: (id, data) => api.put(`/venues/${id}`, data),
  delete: (id) => api.delete(`/venues/${id}`),
};

export const groupTypesApi = {
  list: () => api.get('/group-types'),
  create: (data) => api.post('/group-types', data),
  delete: (id) => api.delete(`/group-types/${id}`),
};

// ---- DASHBOARD ----
export const dashboardApi = {
  stats: (params) => api.get('/dashboard/stats', { params }),
  actionItems: (params) => api.get('/dashboard/action-items', { params }),
};

// ---- PUBLIC ----
export const publicApi = {
  events: (params) => api.get('/public/events', { params }),
  venues: () => api.get('/public/venues'),
  products: (params) => api.get('/public/products', { params }),
  createOrder: (data) => api.post('/public/orders', data),
  bookEvent: (data) => api.post('/public/bookings/event', data),
  bookSpace: (data) => api.post('/public/bookings/space', data),
  checkStatus: (params) => api.get('/public/bookings/status', { params }),
};

// ---- KIOSK ----
export const kioskApi = {
  checkin: (data) => api.post('/kiosk/checkin', data),
  lookup: (identifier) => api.get('/kiosk/lookup', { params: { identifier } }),
  pinCheckin: (data) => api.post('/kiosk/pin-checkin', data),
  // Device management
  listDevices: () => api.get('/kiosk/devices'),
  registerDevice: (data) => api.post('/kiosk/devices', data),
  updateDevice: (id, data) => api.put(`/kiosk/devices/${id}`, data),
  deleteDevice: (id) => api.delete(`/kiosk/devices/${id}`),
  unlockDevice: (id, password) => api.post(`/kiosk/devices/${id}/unlock`, { password }),
};

// ---- FINANCIAL ----
export const financialApi = {
  summary: (location_id) => api.get('/financial/summary', { params: location_id ? { location_id } : {} }),
  accounts: (params) => api.get('/financial/accounts', { params }),
  campusAccounts: (campusId) => api.get(`/financial/campus-accounts/${campusId}`),
  updateAccount: (id, data) => api.put(`/financial/campus-accounts/${id}`, data),
  transfers: (params) => api.get('/financial/transfers', { params }),
  createTransfer: (data) => api.post('/financial/transfers', data),
  budgets: (params) => api.get('/financial/budgets', { params }),
  createBudget: (data) => api.post('/financial/budgets', data),
  categories: () => api.get('/financial/categories'),
  createCategory: (data) => api.post('/financial/categories', data),
  deleteCategory: (id) => api.delete(`/financial/categories/${id}`),
  donations: (params) => api.get('/financial/donations', { params }),
  createDonation: (data) => api.post('/financial/donations', data),
  expenses: (params) => api.get('/financial/expenses', { params }),
  createExpense: (data) => api.post('/financial/expenses', data),
  distributeFunds: (data) => api.post('/financial/distribute-funds', data),
  pendingExpenses: () => api.get('/financial/expenses/pending'),
  approveExpense: (id, comment) => api.put(`/financial/expenses/${id}/approve`, { comment }),
  rejectExpense: (id, comment) => api.put(`/financial/expenses/${id}/reject`, { comment }),
  balanceSheet: (params) => api.get('/financial/balance-sheet', { params }),
  setReceiptUrl: (expenseId, data) => api.put(`/financial/expenses/${expenseId}/receipt-url`, data),
  deleteDonation: (id) => api.delete(`/financial/donations/${id}`),
  deleteExpense: (id) => api.delete(`/financial/expenses/${id}`),
  updateDonation: (id, data) => api.put(`/financial/donations/${id}`, data),
  // Assets
  listAssets: (params) => api.get('/financial/assets', { params }),
  createAsset: (data) => api.post('/financial/assets', data),
  updateAsset: (id, data) => api.put(`/financial/assets/${id}`, data),
  deleteAsset: (id) => api.delete(`/financial/assets/${id}`),
  importExport: (data) => api.post('/financial/import', data),
  // Sponsorship
  listSponsors: (params) => api.get('/financial/sponsors', { params }),
  createSponsor: (data) => api.post('/financial/sponsors', data),
  getSponsor: (id) => api.get(`/financial/sponsors/${id}`),
  updateSponsor: (id, data) => api.put(`/financial/sponsors/${id}`, data),
  deleteSponsor: (id) => api.delete(`/financial/sponsors/${id}`),
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
  delete: (id) => api.delete(`/sales/${id}`),
  export: (params) => api.get('/sales/export', { params }),
  import: (data) => api.post('/sales/import', data),
};

export const customersApi = {
  list: (params) => api.get('/customers', { params }),
  get: (id) => api.get(`/customers/${id}`),
  create: (data) => api.post('/customers', data),
  update: (id, data) => api.put(`/customers/${id}`, data),
  delete: (id) => api.delete(`/customers/${id}`),
  purchases: (id) => api.get(`/customers/${id}/purchases`),
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
  bulkUpdate: (ids, updates) => api.put('/families/bulk-update', { ids, updates }),
  bulkDelete: (ids) => api.post('/families/bulk-delete', { ids }),
};
export const childrenApi = {
  list: (params) => api.get('/children', { params }),
  create: (data) => api.post('/children', data),
  update: (id, data) => api.put(`/children/${id}`, data),
  delete: (id) => api.delete(`/children/${id}`),
  bulkUpdate: (ids, updates) => api.put('/children/bulk-update', { ids, updates }),
  bulkDelete: (ids) => api.post('/children/bulk-delete', { ids }),
  updateEducation: (id, data) => api.put(`/children/${id}/education`, data),
  addReportCard: (id, data) => api.post(`/children/${id}/report-card`, data),
  setResidency: (id, data) => api.put(`/children/${id}/residency`, data),
  getFullProfile: (id) => api.get(`/children/${id}/full-profile`),
};
export const guestsApi = {
  list: (params) => api.get('/guests', { params }),
  create: (data) => api.post('/guests', data),
  update: (id, data) => api.put(`/guests/${id}`, data),
  delete: (id) => api.delete(`/guests/${id}`),
  bulkUpdate: (ids, updates) => api.put('/guests/bulk-update', { ids, updates }),
  bulkDelete: (ids) => api.post('/guests/bulk-delete', { ids }),
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

// ---- STORE SETTINGS ----
export const storeSettingsApi = {
  get: (locationId) => api.get(`/store-settings/${locationId}`),
  update: (locationId, data) => api.put(`/store-settings/${locationId}`, data),
  listAll: () => api.get('/store-settings'),
};

// ---- NOTIFICATIONS ----
export const notificationsApi = {
  list: () => api.get('/notifications'),
  unreadCount: () => api.get('/notifications/unread-count'),
  create: (data) => api.post('/notifications', data),
  markRead: (id) => api.put(`/notifications/${id}/read`),
  markAllRead: () => api.put('/notifications/read-all'),
  delete: (id) => api.delete(`/notifications/${id}`),
  // Push notification features
  vapidKey: () => api.get('/notifications/vapid-key'),
  subscribe: (data) => api.post('/notifications/subscribe', data),
  unsubscribe: () => api.delete('/notifications/subscribe'),
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
  ical: () => `${BACKEND_URL}/api/events/export/ical`,
  icalImport: (data) => api.post('/events/import/ical', data),
  generateRecurring: (data) => api.post('/events/generate-recurring', data),
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
  generateRecurring: (data) => api.post('/events/generate-recurring', data),
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

// ---- ANALYTICS (Basic) ----
export const basicAnalyticsApi = {
  attendance: () => api.get('/analytics/attendance'),
  sales: () => api.get('/analytics/sales'),
  locations: () => api.get('/analytics/locations'),
};

// ---- FINANCIAL EXTRAS ----
export const financialExtrasApi = {
  cashflow: (months) => api.get('/financial/cashflow', { params: { months } }),
  getBalance: () => api.get('/financial/balance'),
  setBalance: (opening_balance) => api.put('/financial/balance', null, { params: { opening_balance } }),
  export: (params) => api.get('/financial/export', { params }),
  import: (data) => api.post('/financial/import', data),
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
  deleteConversation: (convId) => api.delete(`/chat/conversations/${convId}`),
  updateGroupMembers: (convId, data) => api.put(`/chat/conversations/${convId}/members`, data),
  messages: (convId, params) => api.get(`/chat/conversations/${convId}/messages`, { params }),
  sendMessage: (convId, text, threadId = null) => api.post(`/chat/conversations/${convId}/messages`, { text, thread_id: threadId }),
  deleteMessage: (msgId) => api.delete(`/chat/messages/${msgId}`),
  aiAssistant: (message, session_id) => api.post('/chat/ai-assistant', { message, session_id }),
  users: () => api.get('/chat/users'),
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
  guestPasses: (params) => api.get('/access/guest-passes', { params }),
  validateGuestPass: (passId) => api.get(`/access/guest-passes/${passId}/validate`),
  extendGuestPass: (passId, data) => api.put(`/access/guest-passes/${passId}/extend`, data),
  eligibleResidents: (locationId) => api.get(`/access/eligible-residents/${locationId}`),
  // API connections for door/access control systems
  listApiConnections: () => api.get('/access/api-connections'),
  createApiConnection: (data) => api.post('/access/api-connections', data),
  updateApiConnection: (id, data) => api.put(`/access/api-connections/${id}`, data),
  deleteApiConnection: (id) => api.delete(`/access/api-connections/${id}`),
  // Shareable guest access links
  listGuestLinks: () => api.get('/access/guest-links'),
  createGuestLink: (data) => api.post('/access/guest-links', data),
  deleteGuestLink: (id) => api.delete(`/access/guest-links/${id}`),
};

// ---- REPORTS ----
// (consolidated in advanced reports below)

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
  userDirectory: () => api.get('/admin/users/directory'),
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
  bulkDeleteItems: (ids) => api.post('/admin/deleted-items/bulk-delete', { ids }),
  bulkRestoreItems: (ids) => api.post('/admin/deleted-items/bulk-restore', { ids }),
  globalSettings: () => api.get('/global-settings'),
  updateGlobalSettings: (data) => api.put('/global-settings', data),
  currencies: () => api.get('/currencies'),
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

// ---- EMAIL ----
export const emailApi = {
  send: (data) => api.post('/email/send', data),
  log: (params) => api.get('/email/log', { params }),
  templates: () => api.get('/email/templates'),
};

// ---- ADVANCED REPORTS ----
export const reportsApi = {
  summary: (params) => api.get('/reports/summary', { params }),
  campusComparison: (params) => api.get('/reports/campus-comparison', { params }),
  campusDetail: (locationId, params) => api.get(`/reports/campus/${locationId}`, { params }),
  pdf: (params) => api.get('/reports/pdf', { params, responseType: 'blob' }),
};

// ---- ANALYTICS ----
export const analyticsApi = {
  overview: (months) => api.get('/analytics/overview', { params: { months } }),
  trends: (months) => api.get('/analytics/trends', { params: { months } }),
  locationBreakdown: () => api.get('/analytics/location-breakdown'),
  memberGrowth: (months) => api.get('/analytics/member-growth', { params: { months } }),
  outreachImpact: () => api.get('/analytics/outreach-impact'),
};

// ---- REPORT BUILDER ----
export const reportBuilderApi = {
  list: () => api.get('/reports'),
  get: (id) => api.get(`/reports/${id}`),
  create: (data) => api.post('/reports', data),
  update: (id, data) => api.put(`/reports/${id}`, data),
  delete: (id) => api.delete(`/reports/${id}`),
  generate: (id) => api.post(`/reports/${id}/generate`),
  exportXlsx: (id) => `${BACKEND_URL}/api/reports/${id}/export/xlsx`,
};

// ---- VOLUNTEER SCHEDULING ----
export const volunteerApi = {
  shifts: (params) => api.get('/volunteer/shifts', { params }),
  createShift: (data) => api.post('/volunteer/shifts', data),
  updateShift: (id, data) => api.put(`/volunteer/shifts/${id}`, data),
  deleteShift: (id) => api.delete(`/volunteer/shifts/${id}`),
  assignVolunteer: (shiftId, data) => api.post(`/volunteer/shifts/${shiftId}/assign`, data),
  unassignVolunteer: (shiftId, memberId) => api.delete(`/volunteer/shifts/${shiftId}/assign/${memberId}`),
  myShifts: () => api.get('/volunteer/my-shifts'),
};

// ---- EMAIL TEMPLATES ----
export const emailTemplatesApi = {
  list: () => api.get('/email-templates'),
  create: (data) => api.post('/email-templates', data),
  update: (id, data) => api.put(`/email-templates/${id}`, data),
  delete: (id) => api.delete(`/email-templates/${id}`),
  send: (id, data) => api.post(`/email-templates/${id}/send`, data),
};

// ---- GOOGLE AUTH ----
export const googleAuthApi = {
  login: (token) => api.post('/auth/google', { token }),
};

// ---- 2FA ----
export const twoFactorApi = {
  setup: () => api.post('/auth/2fa/setup'),
  verify: (code) => api.post('/auth/2fa/verify', { code }),
  validate: (userId, code) => api.post('/auth/2fa/validate', { user_id: userId, code }),
  disable: () => api.delete('/auth/2fa'),
};

// ---- GDPR ----
export const gdprApi = {
  settings: () => api.get('/gdpr/settings'),
  updateSettings: (data) => api.put('/gdpr/settings', data),
  exportMyData: () => api.post('/gdpr/export-my-data'),
  anonymize: (userId) => api.post(`/gdpr/anonymize/${userId}`),
};

// ---- INVENTORY ALERTS ----
export const inventoryApi = {
  alerts: () => api.get('/inventory/alerts'),
};

// ---- ADMIN CONFIG ----
export const configApi = {
  getRoles: () => api.get('/config/roles'),
  updateRoles: (roles) => api.put('/config/roles', { roles }),
  getDocTypes: () => api.get('/config/document-types'),
  updateDocTypes: (types) => api.put('/config/document-types', { types }),
  getRestrictedSpaces: (campusId) => api.get('/restricted-spaces', { params: { campus_id: campusId } }),
  addStaffToRestricted: (spaceId, staffIds) => api.post(`/restricted-spaces/${spaceId}/staff`, { staff_ids: staffIds }),
  removeStaffFromRestricted: (spaceId, staffId) => api.delete(`/restricted-spaces/${spaceId}/staff/${staffId}`),
  addResidents: (spaceId, residentIds) => api.post(`/restricted-spaces/${spaceId}/residents`, { resident_ids: residentIds }),
  getResidents: (spaceId) => api.get(`/restricted-spaces/${spaceId}/residents`),
  getVolunteerAttendees: (eventId) => api.get(`/volunteer/event-attendees/${eventId}`),
};


// ---- FINANCIAL APIS ----
export const financialApisApi = {
  list: () => api.get('/financial-apis'),
  create: (data) => api.post('/financial-apis', data),
  update: (id, data) => api.put(`/financial-apis/${id}`, data),
  delete: (id) => api.delete(`/financial-apis/${id}`),
};

// ---- I18N ----
export const i18nApi = {
  getTranslations: (lang) => api.get(`/i18n/${lang}`),
  getAll: () => api.get('/i18n'),
};

// ---- WEBCAL ----
export const webcalApi = {
  feedUrl: (userId) => `${BACKEND_URL}/api/webcal/${userId}.ics`,
};

// ---- CALLING ----
export const callingApi = {
  // Extensions
  listExtensions: () => api.get('/calling/extensions'),
  createExtension: (data) => api.post('/calling/extensions', data),
  updateExtension: (ext, data) => api.put(`/calling/extensions/${ext}`, data),
  deleteExtension: (ext) => api.delete(`/calling/extensions/${ext}`),
  getUserExtension: (userId) => api.get(`/calling/extensions/user/${userId}`),
  
  // PBX Configuration
  listPbxConfigs: () => api.get('/calling/pbx-configs'),
  getSipCredentials: () => api.get('/calling/pbx-configs/sip-credentials'),
  createPbxConfig: (data) => api.post('/calling/pbx-configs', data),
  updatePbxConfig: (id, data) => api.put(`/calling/pbx-configs/${id}`, data),
  deletePbxConfig: (id) => api.delete(`/calling/pbx-configs/${id}`),
  testPbxConnection: (id) => api.post(`/calling/pbx-configs/${id}/test`),
  
  // Calls
  initiateCall: (data, userId) => api.post(`/calling/calls/initiate?user_id=${userId}`, data),
  callAction: (callId, data, userId) => api.post(`/calling/calls/${callId}/action?user_id=${userId}`, data),
  getActiveCalls: (userId) => api.get(`/calling/calls/active?user_id=${userId}`),
  startRecording: (callId) => api.post(`/calling/calls/${callId}/recording/start`),
  stopRecording: (callId) => api.post(`/calling/calls/${callId}/recording/stop`),
  
  // Call History
  getHistory: (userId, params = {}) => api.get(`/calling/history?user_id=${userId}`, { params }),
  getCallDetail: (callId) => api.get(`/calling/history/${callId}`),
  deleteCallRecord: (callId) => api.delete(`/calling/history/${callId}`),
  
  // Voicemail
  getVoicemails: (userId, unreadOnly = false) => api.get(`/calling/voicemail?user_id=${userId}&unread_only=${unreadOnly}`),
  markVoicemailRead: (id) => api.put(`/calling/voicemail/${id}/read`),
  deleteVoicemail: (id) => api.delete(`/calling/voicemail/${id}`),
  getUnreadVoicemailCount: (userId) => api.get(`/calling/voicemail/unread-count?user_id=${userId}`),
  
  // Recordings
  getRecordings: (userId, limit = 50) => api.get(`/calling/recordings?user_id=${userId}&limit=${limit}`),
  saveRecording: (callId, url) => api.post(`/calling/recordings/${callId}/save`, { recording_url: url }),
  
  // Status
  updateStatus: (userId, status) => api.put(`/calling/status?user_id=${userId}&status=${status}`),
  getUserStatus: (userId) => api.get(`/calling/status/${userId}`),
  
  // Missed Calls
  getMissedCalls: (userId) => api.get(`/calling/missed?user_id=${userId}`),
  getMissedCallCount: (userId) => api.get(`/calling/missed/count?user_id=${userId}`),
  markMissedCallsSeen: (userId) => api.put(`/calling/missed/mark-seen?user_id=${userId}`),
  
  // Contacts
  getCallableContacts: (userId) => api.get(`/calling/contacts?user_id=${userId}`),
  
  // ICE Servers
  getIceServers: () => api.get('/calling/ice-servers'),
  // Auto-Attendant
  getAutoAttendant: () => api.get('/calling/auto-attendant'),
  updateAutoAttendant: (data) => api.put('/calling/auto-attendant', data),
  // Call Queues
  listQueues: () => api.get('/calling/queues'),
  createQueue: (data) => api.post('/calling/queues', data),
  updateQueue: (id, data) => api.put(`/calling/queues/${id}`, data),
  deleteQueue: (id) => api.delete(`/calling/queues/${id}`),
  // Call Forwarding
  getForwarding: (userId) => api.get(`/calling/forwarding/${userId}`),
  updateForwarding: (userId, data) => api.put(`/calling/forwarding/${userId}`, data),
  // Outgoing Rules
  listOutgoingRules: () => api.get('/calling/outgoing-rules'),
  createOutgoingRule: (data) => api.post('/calling/outgoing-rules', data),
  deleteOutgoingRule: (id) => api.delete(`/calling/outgoing-rules/${id}`),
};

// ---- PRESENCE ----
export const presenceApi = {
  getStatus: (userId) => api.get(`/presence/status/${userId}`),
  getBulkStatus: (userIds) => api.get(`/presence/bulk?user_ids=${userIds.join(',')}`),
  heartbeat: (userId) => api.put(`/presence/heartbeat?user_id=${userId}`),
  setStatus: (userId, status, message = '') => api.put(`/presence/status?user_id=${userId}&status=${status}${message ? `&status_message=${message}` : ''}`),
  getOnlineUsers: () => api.get('/presence/online-users'),
};

// ---- CONFERENCES ----
export const conferencesApi = {
  list: (userId, includePast = false) => api.get(`/conferences?user_id=${userId}&include_past=${includePast}`),
  create: (data, userId) => api.post(`/conferences?user_id=${userId}`, data),
  get: (id) => api.get(`/conferences/${id}`),
  update: (id, data, userId) => api.put(`/conferences/${id}?user_id=${userId}`, data),
  delete: (id, userId) => api.delete(`/conferences/${id}?user_id=${userId}`),
  invite: (id, userIds, externalInvites, userId) => api.post(`/conferences/${id}/invite?user_id=${userId}`, { user_ids: userIds, external_invites: externalInvites }),
  join: (id, data, userId = null) => api.post(`/conferences/${id}/join${userId ? `?user_id=${userId}` : ''}`, data),
  leave: (id, userId) => api.post(`/conferences/${id}/leave?user_id=${userId}`),
  end: (id, userId) => api.post(`/conferences/${id}/end?user_id=${userId}`),
  getParticipants: (id) => api.get(`/conferences/${id}/participants`),
  startRecording: (id, userId) => api.post(`/conferences/${id}/recording/start?user_id=${userId}`),
  stopRecording: (id, userId) => api.post(`/conferences/${id}/recording/stop?user_id=${userId}`),
  createInstant: (title, userId) => api.post(`/conferences/instant?title=${encodeURIComponent(title)}&user_id=${userId}`),
  getAvailableSlots: (userIds, date, duration = 60) => api.get(`/conferences/schedule/available-slots?user_ids=${userIds.join(',')}&date=${date}&duration_minutes=${duration}`),
};

// ---- REACTIONS ----
export const reactionsApi = {
  getQuickReactions: () => api.get('/reactions/quick'),
  addReaction: (messageId, emoji, userId) => api.post(`/reactions/message/${messageId}?emoji=${encodeURIComponent(emoji)}&user_id=${userId}`),
  removeReaction: (messageId, emoji, userId) => api.delete(`/reactions/message/${messageId}?emoji=${encodeURIComponent(emoji)}&user_id=${userId}`),
  getMessageReactions: (messageId) => api.get(`/reactions/message/${messageId}`),
  getRecentReactions: (conversationId, limit = 10) => api.get(`/reactions/conversation/${conversationId}/recent?limit=${limit}`),
};

// ---- WAVE (Grandstream CloudUCM) ----
export const waveApi = {
  listServers: () => api.get('/wave/servers'),
  addServer: (data) => api.post('/wave/servers', data),
  updateServer: (id, data) => api.put(`/wave/servers/${id}`, data),
  deleteServer: (id) => api.delete(`/wave/servers/${id}`),
  getMyConfig: () => api.get('/wave/my-config'),
  saveMyCredentials: (data) => api.put('/wave/my-credentials', data),
};

