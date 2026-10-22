import { useId } from 'react';

const back = 'M2.5 16A13.5 5 0 0 1 29.5 16';
const front = 'M29.5 16A13.5 5 0 0 1 2.5 16';
const orbit = 'M29.5 16A13.5 5 0 0 1 2.5 16A13.5 5 0 0 1 29.5 16';

export default function Logo({ className = '', thinking = false }: { className?: string; thinking?: boolean }) {
  const gradient = `aster-planet-${useId().replace(/[^\w-]/g, '')}`;
  return <svg className={`logo ${thinking ? 'thinking' : ''} ${className}`.trim()} viewBox="0 0 32 32" aria-hidden="true">
    <defs>
      <radialGradient id={gradient} cx="35%" cy="30%" r="75%">
        <stop offset="0" style={{ stopColor: 'var(--planet-light)' }} />
        <stop offset=".38" style={{ stopColor: 'var(--planet-base)' }} />
        <stop offset="1" style={{ stopColor: 'var(--planet-shade)' }} />
      </radialGradient>
    </defs>
    <g transform="rotate(-22 16 16)">
      <path className="logo-ring" d={back} />
      <circle className="logo-planet" cx="16" cy="16" r="7.2" fill={`url(#${gradient})`} />
      <path className="logo-ring" d={front} />
      <circle className="logo-moon" cx="27.4" cy="18.6" r="1.9" />
      {thinking && <circle className="logo-moon logo-orbiting" r="1.9"><animateMotion dur="2.4s" repeatCount="indefinite" path={orbit} /></circle>}
    </g>
  </svg>;
}
