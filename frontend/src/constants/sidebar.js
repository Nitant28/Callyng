export const SIDEBAR_NAV = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    path: '/app',
    icon: 'dashboard',
    enabled: true,
    match: (path) => path === '/app',
  },
  {
    id: 'campaigns',
    label: 'Campaigns',
    path: '/app/campaigns',
    icon: 'campaign',
    enabled: true,
    match: (path) => path.startsWith('/app/campaigns'),
  },
  {
    id: 'messages',
    label: 'Messages',
    path: '/app/messages',
    icon: 'chat',
    enabled: true,
    match: (path) => path.startsWith('/app/messages'),
  },
];
