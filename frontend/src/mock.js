// Mock data for 58:12 Global Connect CRM

export const MOCK_USER = {
  id: 'usr_001',
  name: 'Admin User',
  email: 'admin@5812global.org',
  role: 'admin',
  avatar: null,
};

export const MOCK_MEMBERS = [
  { id: 'mem_001', name: 'Alice Namukasa', email: 'alice@example.com', phone: '+256 700 123456', nationalId: 'CM900001000XXXX', role: 'Member', status: 'active', joinDate: '2024-01-15', group: 'Youth', gender: 'female' },
  { id: 'mem_002', name: 'Brian Ssekitto', email: 'brian@example.com', phone: '+256 752 234567', nationalId: 'CM850002000XXXX', role: 'Staff', status: 'active', joinDate: '2023-06-10', group: 'Leadership', gender: 'male' },
  { id: 'mem_003', name: 'Catherine Nakato', email: 'catherine@example.com', phone: '+256 781 345678', nationalId: 'CM920003000XXXX', role: 'Member', status: 'active', joinDate: '2024-03-20', group: 'Women', gender: 'female' },
  { id: 'mem_004', name: 'David Kiggundu', email: 'david@example.com', phone: '+256 706 456789', nationalId: 'CM880004000XXXX', role: 'Volunteer', status: 'active', joinDate: '2023-11-05', group: 'Volunteers', gender: 'male' },
  { id: 'mem_005', name: 'Esther Namirembe', email: 'esther@example.com', phone: '+256 773 567890', nationalId: 'CM950005000XXXX', role: 'Member', status: 'inactive', joinDate: '2022-08-30', group: 'Youth', gender: 'female' },
  { id: 'mem_006', name: 'Francis Tumwesigye', email: 'francis@example.com', phone: '+256 712 678901', nationalId: 'CM780006000XXXX', role: 'Leader', status: 'active', joinDate: '2021-05-12', group: 'Leadership', gender: 'male' },
  { id: 'mem_007', name: 'Grace Akello', email: 'grace@example.com', phone: '+256 756 789012', nationalId: 'CM960007000XXXX', role: 'Member', status: 'active', joinDate: '2024-07-01', group: 'Youth', gender: 'female' },
  { id: 'mem_008', name: 'Henry Wasswa', email: 'henry@example.com', phone: '+256 701 890123', nationalId: 'CM820008000XXXX', role: 'Staff', status: 'active', joinDate: '2023-01-18', group: 'Admin', gender: 'male' },
  { id: 'mem_009', name: 'Irene Nabatanzi', email: 'irene@example.com', phone: '+256 784 901234', nationalId: 'CM990009000XXXX', role: 'Member', status: 'active', joinDate: '2025-01-10', group: 'Women', gender: 'female' },
  { id: 'mem_010', name: 'Joseph Muwanguzi', email: 'joseph@example.com', phone: '+256 715 012345', nationalId: 'CM870010000XXXX', role: 'Volunteer', status: 'inactive', joinDate: '2022-04-22', group: 'Volunteers', gender: 'male' },
];

export const MOCK_EVENTS = [
  { id: 'evt_001', title: 'Sunday Service', type: 'service', status: 'upcoming', date: '2026-04-06', time: '09:00', endTime: '11:30', location: '58:12 Global Centre', capacity: 300, registered: 212, description: 'Weekly Sunday worship service open to all.', isPublic: true, isFree: true },
  { id: 'evt_002', title: 'Youth Leadership Summit', type: 'conference', status: 'upcoming', date: '2026-04-12', time: '10:00', endTime: '17:00', location: 'Kampala Conference Hall', capacity: 100, registered: 87, description: 'Annual leadership development summit for youth ages 18-35.', isPublic: true, isFree: false, price: 25000 },
  { id: 'evt_003', title: 'Community Outreach', type: 'community', status: 'upcoming', date: '2026-04-19', time: '08:00', endTime: '14:00', location: 'Nakawa Market Area', capacity: 50, registered: 34, description: 'Community service outreach program in the Nakawa district.', isPublic: false, isFree: true },
  { id: 'evt_004', title: 'Women in Faith Conference', type: 'conference', status: 'upcoming', date: '2026-04-26', time: '09:00', endTime: '16:00', location: '58:12 Global Centre', capacity: 150, registered: 102, description: 'Annual conference empowering women in their faith journey.', isPublic: true, isFree: false, price: 15000 },
  { id: 'evt_005', title: 'Staff Meeting', type: 'meeting', status: 'upcoming', date: '2026-04-02', time: '14:00', endTime: '16:00', location: 'Admin Block', capacity: 20, registered: 15, description: 'Monthly all-staff meeting.', isPublic: false, isFree: true },
  { id: 'evt_006', title: 'Easter Sunday Service', type: 'service', status: 'completed', date: '2026-03-31', time: '07:00', endTime: '11:00', location: '58:12 Global Centre', capacity: 500, registered: 487, description: 'Easter Sunday special service.', isPublic: true, isFree: true },
  { id: 'evt_007', title: 'QR Test Event', type: 'meeting', status: 'upcoming', date: '2026-04-01', time: '10:00', endTime: '12:00', location: 'Tech Lab', capacity: 100, registered: 11, description: 'Event for testing QR code check-in system.', isPublic: true, isFree: true },
];

export const MOCK_VENUES = [
  { id: 'ven_001', name: 'Main Auditorium', capacity: 500, type: 'auditorium', available: true, hourlyRate: null, description: 'Main worship hall with full AV system.' },
  { id: 'ven_002', name: 'Conference Room A', capacity: 40, type: 'conference', available: true, hourlyRate: 20000, description: 'Small conference room with projector and whiteboard.' },
  { id: 'ven_003', name: 'Youth Hall', capacity: 150, type: 'hall', available: false, hourlyRate: 50000, description: 'Large multipurpose hall for youth activities.' },
  { id: 'ven_004', name: 'Prayer Garden', capacity: 30, type: 'outdoor', available: true, hourlyRate: null, description: 'Peaceful outdoor garden space.' },
];

export const MOCK_TASKS = [
  { id: 'task_001', title: 'Prepare Easter sermon notes', description: 'Compile and format sermon notes for Easter service', status: 'done', priority: 'high', assignee: 'Brian Ssekitto', dueDate: '2026-03-30', tags: ['sermon', 'easter'] },
  { id: 'task_002', title: 'Send membership renewal reminders', description: 'Email all members whose membership expires in April', status: 'in-progress', priority: 'high', assignee: 'Henry Wasswa', dueDate: '2026-04-05', tags: ['membership', 'email'] },
  { id: 'task_003', title: 'Set up Youth Summit registration', description: 'Configure online registration for Youth Leadership Summit', status: 'in-progress', priority: 'medium', assignee: 'Alice Namukasa', dueDate: '2026-04-08', tags: ['events', 'registration'] },
  { id: 'task_004', title: 'Update website event listings', description: 'Add upcoming April events to the website', status: 'todo', priority: 'medium', assignee: 'Grace Akello', dueDate: '2026-04-10', tags: ['website', 'events'] },
  { id: 'task_005', title: 'Volunteer coordination for outreach', description: 'Assign volunteers to different stations for the community outreach', status: 'todo', priority: 'high', assignee: 'David Kiggundu', dueDate: '2026-04-15', tags: ['volunteers', 'outreach'] },
  { id: 'task_006', title: 'Purchase office supplies', description: 'Order new printer cartridges, paper, and stationery', status: 'todo', priority: 'low', assignee: 'Irene Nabatanzi', dueDate: '2026-04-20', tags: ['admin', 'supplies'] },
  { id: 'task_007', title: 'Finalize Women Conference speakers', description: 'Confirm all 5 speakers for the Women in Faith Conference', status: 'in-progress', priority: 'high', assignee: 'Catherine Nakato', dueDate: '2026-04-12', tags: ['events', 'speakers'] },
  { id: 'task_008', title: 'Monthly financial report', description: 'Compile March financial report for board review', status: 'done', priority: 'high', assignee: 'Francis Tumwesigye', dueDate: '2026-04-05', tags: ['finance', 'reports'] },
];

export const MOCK_CHECKINS = [
  { id: 'ci_001', memberId: 'mem_001', memberName: 'Alice Namukasa', type: 'member', eventName: 'Sunday Service', checkInTime: '2026-03-31T08:45:00Z', method: 'qr' },
  { id: 'ci_002', memberId: 'mem_002', memberName: 'Brian Ssekitto', type: 'staff', eventName: 'Sunday Service', checkInTime: '2026-03-31T07:30:00Z', method: 'manual' },
  { id: 'ci_003', memberId: null, memberName: 'Visitor - John Doe', type: 'visitor', eventName: 'Sunday Service', checkInTime: '2026-03-31T09:05:00Z', method: 'manual' },
  { id: 'ci_004', memberId: 'mem_003', memberName: 'Catherine Nakato', type: 'member', eventName: 'Sunday Service', checkInTime: '2026-03-31T09:10:00Z', method: 'id' },
];

export const MOCK_STATS = {
  totalMembers: 1247,
  activeMembers: 1089,
  eventsThisMonth: 8,
  checkInsToday: 43,
  tasksOverdue: 3,
  upcomingEvents: 5,
  newMembersThisMonth: 12,
  volunteerHours: 284,
};

export const MOCK_ACTIVITY = [
  { id: 1, type: 'checkin', message: 'Alice Namukasa checked in to Sunday Service', time: '2 minutes ago' },
  { id: 2, type: 'event', message: 'Youth Leadership Summit registration opened', time: '1 hour ago' },
  { id: 3, type: 'member', message: 'New member: Irene Nabatanzi registered', time: '3 hours ago' },
  { id: 4, type: 'task', message: 'Task "Monthly financial report" marked complete', time: '5 hours ago' },
  { id: 5, type: 'checkin', message: '45 check-ins for Easter Sunday Service', time: '2 days ago' },
];

export const MOCK_GROUPS = ['Youth', 'Women', 'Leadership', 'Volunteers', 'Admin', 'Children', 'Seniors', 'Choir'];
export const MOCK_ROLES = ['Executive Director', 'Advisor', 'Director', 'Manager', 'Coordinator', 'Staff', 'Intern', 'Volunteer', 'Parent', 'Customer'];
