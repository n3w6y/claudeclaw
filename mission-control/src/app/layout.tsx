import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/Sidebar';

export const metadata: Metadata = {
  title: 'Mission Control',
  description: 'TinyClaw Agent Dashboard',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-gray-950 text-gray-100 font-mono flex">
        <Sidebar />
        <main className="flex-1 min-w-0 overflow-hidden">{children}</main>
      </body>
    </html>
  );
}
