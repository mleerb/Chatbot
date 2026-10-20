import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'AGENTslop',
  description: 'A local AI agent chatbot for questions, ideas, writing, planning, and working with files.',
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
