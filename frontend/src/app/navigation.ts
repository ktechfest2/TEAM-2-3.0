import {
  BarChart3Icon,
  ClipboardCheckIcon,
  FileStackIcon,
  HomeIcon,
  InfoIcon,
  LayoutDashboardIcon,
  MapPinIcon,
  MegaphoneIcon,
  ScrollTextIcon,
  SettingsIcon,
  SirenIcon,
  TriangleAlertIcon,
  type LucideIcon,
} from 'lucide-react'
import { ADMIN_CONSOLE_ROLES, EVIDENCE_REVIEWER_ROLES, EVIDENCE_STAFF_ROLES, type Role } from '@/features/auth/roles'

export type NavItem = {
  label: string
  to: string
  icon: LucideIcon
  /** Match only the exact path (for index routes). */
  end?: boolean
}

export type AdminNavItem = NavItem & {
  roles: readonly Role[]
  group: 'Operations' | 'Governance'
}

export const PUBLIC_NAV: NavItem[] = [
  { label: 'Home', to: '/', icon: HomeIcon, end: true },
  { label: 'Find polling unit', to: '/polling-units', icon: MapPinIcon },
  { label: 'Results', to: '/results', icon: BarChart3Icon },
  { label: 'How verification works', to: '/verification', icon: InfoIcon },
  { label: 'Updates', to: '/updates', icon: MegaphoneIcon },
]

export const REPORT_INCIDENT_NAV: NavItem = {
  label: 'Report an incident',
  to: '/report-incident',
  icon: TriangleAlertIcon,
}

export const ADMIN_NAV: AdminNavItem[] = [
  {
    label: 'Overview',
    to: '/admin',
    icon: LayoutDashboardIcon,
    end: true,
    roles: ADMIN_CONSOLE_ROLES,
    group: 'Operations',
  },
  {
    label: 'Results',
    to: '/admin/results',
    icon: BarChart3Icon,
    roles: ['reviewer', 'auditor', 'election_admin', 'system_admin'],
    group: 'Operations',
  },
  {
    label: 'Evidence submissions',
    to: '/admin/evidence',
    icon: FileStackIcon,
    roles: EVIDENCE_STAFF_ROLES,
    group: 'Operations',
  },
  {
    label: 'Verification review',
    to: '/admin/verification',
    icon: ClipboardCheckIcon,
    roles: EVIDENCE_REVIEWER_ROLES,
    group: 'Operations',
  },
  {
    label: 'Incidents',
    to: '/admin/incidents',
    icon: SirenIcon,
    /** Mirrors backend INCIDENT_STAFF_ROLES. Auditors read; only reviewers change status. */
    roles: ['reviewer', 'auditor', 'election_admin', 'system_admin'],
    group: 'Operations',
  },
  {
    label: 'Elections and register',
    to: '/admin/polling-units',
    icon: MapPinIcon,
    roles: ['election_admin', 'system_admin'],
    group: 'Governance',
  },
  {
    label: 'Audit logs',
    to: '/admin/audit-logs',
    icon: ScrollTextIcon,
    roles: ['auditor', 'election_admin', 'system_admin'],
    group: 'Governance',
  },
  {
    label: 'Accounts and roles',
    to: '/admin/settings',
    icon: SettingsIcon,
    roles: ['system_admin'],
    group: 'Governance',
  },
]

export function adminNavItem(to: string): AdminNavItem {
  const item = ADMIN_NAV.find((entry) => entry.to === to)
  if (!item) throw new Error(`Unknown admin route: ${to}`)
  return item
}