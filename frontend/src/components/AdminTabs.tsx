import React from 'react';
import { NavLink } from 'react-router-dom';

const ADMIN_SECTIONS = [
  { to: '/admin', label: 'Documents', end: true },
  { to: '/admin/recruitment', label: 'Recruitment', end: false },
];

/** Switches between the admin console's sections. */
const AdminTabs: React.FC = () => (
  <nav aria-label="Admin sections" className="flex gap-6 border-b border-line">
    {ADMIN_SECTIONS.map((section) => (
      <NavLink
        key={section.to}
        to={section.to}
        end={section.end}
        className={({ isActive }) =>
          `-mb-px border-b-2 pb-2.5 text-sm transition-colors ${
            isActive ? 'border-ink font-medium text-ink' : 'border-transparent text-ink-3 hover:text-ink'
          }`
        }
      >
        {section.label}
      </NavLink>
    ))}
  </nav>
);

export default AdminTabs;
