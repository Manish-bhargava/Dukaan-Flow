import type { ReactNode } from 'react'

/**
 * Local placeholder "photo" of a product pack, used until a real image is uploaded to
 * Cloudinary. The pack shape follows the product type and the label shows the brand,
 * name and pack size, so retailers can still recognise products at a glance.
 */
type Shape = 'wrapper' | 'bar' | 'pouch' | 'box' | 'bottle' | 'carton'

interface Style {
  shape: Shape
  body: string
  accent: string
  label: string // label text colour
}

function styleFor(name: string, category: string): Style {
  const n = name.toLowerCase()
  const c = category.toLowerCase()
  if (n.includes('cream') && c.includes('biscuit')) return { shape: 'wrapper', body: '#c2416b', accent: '#7a1f3d', label: '#fff8f0' }
  if (c.includes('biscuit')) return { shape: 'wrapper', body: '#eea50b', accent: '#8a3f0c', label: '#fffdf7' }
  if (n.includes('liquid') || n.includes('shampoo') || n.includes('oil')) return { shape: 'bottle', body: '#1f9e7a', accent: '#0f5c46', label: '#fffdf7' }
  if (n.includes('bar') || n.includes('soap')) return { shape: 'bar', body: '#2f8f4e', accent: '#fbc124', label: '#fffdf7' }
  if (c.includes('home')) return { shape: 'pouch', body: '#26904f', accent: '#fbc124', label: '#fffdf7' }
  if (c.includes('tea') || c.includes('coffee')) return { shape: 'box', body: '#a23b1d', accent: '#fbc124', label: '#fff3c4' }
  if (c.includes('noodle') || c.includes('snack')) return { shape: 'pouch', body: '#e5532d', accent: '#fbc124', label: '#fffdf7' }
  return { shape: 'carton', body: '#c9a26a', accent: '#8a6a3a', label: '#fffdf7' }
}

/** Up to two lines of ~`width` characters. */
function lines(text: string, width: number): string[] {
  const out: string[] = []
  let current = ''
  for (const word of text.split(/\s+/)) {
    if ((current + ' ' + word).trim().length > width && current) {
      out.push(current)
      current = word
    } else current = (current + ' ' + word).trim()
  }
  if (current) out.push(current)
  return out.length > 2 ? [out[0], `${out.slice(1).join(' ').slice(0, width - 1)}…`] : out
}

export function PackShot({
  name,
  brand,
  category,
  packSize,
  className = 'h-full w-full',
}: {
  name: string
  brand: string
  category: string
  packSize: string
  className?: string
}) {
  const s = styleFor(name, category)
  const title = name.replace(new RegExp(`\\s*${packSize.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`, 'i'), '').trim() || name
  // Text never leaves its label area: long lines are wrapped, then squeezed to fit.
  const fit = (text: string, size: number, maxWidth: number) =>
    text.length * size * 0.58 > maxWidth ? { textLength: maxWidth, lengthAdjust: 'spacingAndGlyphs' as const } : {}
  const label = (cx: number, top: number, maxWidth: number, size = 14): ReactNode => {
    const brandText = brand.toUpperCase()
    return (
      <g fill={s.label} textAnchor="middle" fontFamily="inherit">
        <text x={cx} y={top} fontSize="8" fontWeight="700" opacity="0.85" letterSpacing="0.5" {...fit(brandText, 8, maxWidth)}>
          {brandText}
        </text>
        {lines(title, Math.max(6, Math.floor(maxWidth / (size * 0.58)))).map((line, i) => (
          <text key={i} x={cx} y={top + 17 + i * (size + 2)} fontSize={size} fontWeight="800" {...fit(line, size, maxWidth)}>
            {line}
          </text>
        ))}
      </g>
    )
  }
  const badge = (cx: number, cy: number) => (
    <g>
      <circle cx={cx} cy={cy} r="19" fill={s.accent} stroke="#fffdf7" strokeWidth="2.5" />
      <text x={cx} y={cy + 4.5} textAnchor="middle" fontSize={packSize.length > 4 ? 10 : 12} fontWeight="800" fill={s.accent === '#fbc124' ? '#113f26' : '#fffdf7'} fontFamily="inherit">
        {packSize}
      </text>
    </g>
  )

  const shapes: Record<Shape, ReactNode> = {
    wrapper: (
      <g>
        <path d="M24 62h152v76H24z" fill={s.body} />
        <path d="M24 62l-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6zM176 62l8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6z" fill={s.accent} />
        <rect x="24" y="62" width="152" height="10" fill="#fff" opacity="0.18" />
        <ellipse cx="146" cy="100" rx="22" ry="22" fill={s.accent} opacity="0.35" />
        {label(76, 90, 92)}
        {badge(152, 100)}
      </g>
    ),
    bar: (
      <g>
        <rect x="30" y="62" width="140" height="80" rx="10" fill={s.body} />
        <rect x="30" y="62" width="140" height="10" rx="5" fill="#fff" opacity="0.2" />
        <path d="M30 130h140v2a10 10 0 0 1-10 10H40a10 10 0 0 1-10-10z" fill={s.accent} opacity="0.9" />
        {label(82, 88, 86, 13)}
        {badge(148, 102)}
      </g>
    ),
    pouch: (
      <g>
        <path d="M58 30h84l10 14-6 132H54l-6-132z" fill={s.body} />
        <path d="M58 30h84l10 14H48z" fill={s.accent} />
        <path d="M60 33h80" stroke="#fff" strokeWidth="2" strokeDasharray="3 3" opacity="0.6" />
        <rect x="62" y="60" width="76" height="62" rx="8" fill="#000" opacity="0.12" />
        {label(100, 78, 70)}
        {badge(100, 146)}
      </g>
    ),
    box: (
      <g>
        <path d="M146 44l18-12v130l-18 14z" fill={s.accent} opacity="0.75" />
        <path d="M56 44l18-12h90l-18 12z" fill={s.accent} />
        <rect x="56" y="44" width="90" height="132" fill={s.body} />
        <path d="M101 120c12 2 16 14 8 26-12-2-16-14-8-26z" fill="#47ad70" />
        {label(101, 70, 80)}
        {badge(101, 158)}
      </g>
    ),
    bottle: (
      <g>
        <rect x="88" y="22" width="24" height="16" rx="3" fill={s.accent} />
        <path d="M90 38h20v10l18 18v104a8 8 0 0 1-8 8H80a8 8 0 0 1-8-8V66l18-18z" fill={s.body} />
        <rect x="76" y="82" width="48" height="70" rx="6" fill="#fff" opacity="0.18" />
        {label(100, 98, 44, 11)}
        {badge(100, 160)}
      </g>
    ),
    carton: (
      <g>
        <path d="M40 66l60-24 60 24v84l-60 24-60-24z" fill={s.body} />
        <path d="M40 66l60 24 60-24M100 90v84" fill="none" stroke={s.accent} strokeWidth="2" />
        {label(72, 104, 50, 11)}
        {badge(132, 128)}
      </g>
    ),
  }

  return (
    <svg viewBox="0 0 200 200" className={className} role="img" aria-label={`${name} (illustration)`}>
      <ellipse cx="100" cy="186" rx="62" ry="6" fill="#1d2b22" opacity="0.08" />
      {shapes[s.shape]}
    </svg>
  )
}
