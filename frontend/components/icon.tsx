type Name = 'file' | 'attach' | 'send' | 'menu' | 'close' | 'sun' | 'moon' | 'chat' | 'download' | 'pin' | 'edit' | 'trash' | 'more';

const paths: Record<Name, string> = {
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h5',
  attach: 'm8 12 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l9-9 M7 13l7-7',
  send: 'M12 19V5 M5 12l7-7 7 7',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  close: 'm6 6 12 12 M6 18 18 6',
  sun: 'M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l1.5 1.5 M17.5 17.5 19 19 M5 19l1.5-1.5 M17.5 6.5 19 5 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  moon: 'M20 14A8 8 0 0 1 10 4a8.5 8.5 0 1 0 10 10z',
  chat: 'M21 11a8 8 0 0 1-8 8H7l-5 3V5a3 3 0 0 1 3-3h8a8 8 0 0 1 8 9z M7 8h9 M7 12h6',
  download: 'M12 3v12 M7 10l5 5 5-5 M5 17v4h14v-4',
  pin: 'm16 3 5 5-4 1-4 4-1 4-5-5 4-1 4-4z M8 16l-5 5',
  edit: 'm15 5 4 4 M4 20l4-1L20 7a3 3 0 0 0-4-4L4 15z',
  trash: 'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',
  more: 'M5 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2 M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2 M19 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2',
};

export default function Icon({ name }: { name: Name }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
