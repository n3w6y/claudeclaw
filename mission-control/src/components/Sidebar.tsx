'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { href: '/activity', label: 'Activity', icon: '>' },
  { href: '/trading', label: 'Trading', icon: '$' },
  { href: '/search', label: 'Search', icon: '?' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setOpen(!open)}
        className="md:hidden fixed top-3 left-3 z-50 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300 hover:text-gray-100"
      >
        {open ? 'x' : '='}
      </button>

      {/* Overlay */}
      {open && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-30"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:static z-40 top-0 left-0 h-full w-52 bg-gray-900 border-r border-gray-800 flex flex-col transition-transform md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="px-4 py-4 border-b border-gray-800">
          <h1 className="text-sm font-bold text-gray-100 tracking-wide">MISSION CONTROL</h1>
          <p className="text-xs text-gray-500 mt-0.5">tinyclaw</p>
        </div>

        <nav className="flex-1 py-2">
          {NAV_ITEMS.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-2 px-4 py-2 text-sm transition-colors ${
                  active
                    ? 'bg-gray-800 text-gray-100 border-r-2 border-blue-400'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                }`}
              >
                <span className="text-xs text-gray-600 w-4">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="px-4 py-3 border-t border-gray-800">
          <div className="flex flex-col gap-1 text-xs text-gray-600">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              elliot
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-400" />
              trader
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-purple-400" />
              dev
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
