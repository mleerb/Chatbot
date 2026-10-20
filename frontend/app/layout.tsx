import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'Aster',
  description: 'A local AI agent chatbot for questions, ideas, writing, planning, and working with files.',
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: `(() => { let saved; try { saved = localStorage.getItem('aster-theme'); } catch {} document.documentElement.dataset.theme = saved === 'light' || saved === 'dark' ? saved : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); })();` }} /></head><body>{children}</body></html>;
}
