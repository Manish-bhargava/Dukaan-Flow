import type { ReactNode } from 'react'
/**
 * Illustrated product packs, so the catalogue looks like a shop shelf without product
 * photos (the seed data has none). Picked by category name; falls back to a carton.
 */
import type { ArtKind } from './productKinds'

export function ProductArt({ kind, label, className = 'h-24 w-24' }: { kind: ArtKind; label?: string; className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} role="img" aria-label={label ?? kind}>
      <ellipse cx="60" cy="108" rx="34" ry="5" fill="#1d2b22" opacity="0.08" />
      {ART[kind]}
      {label && (
        <g>
          <rect x="36" y="94" width="48" height="16" rx="8" fill="#113f26" />
          <text x="60" y="105.5" textAnchor="middle" fontSize="9" fontWeight="800" fill="#fffdf7" fontFamily="inherit">
            {label.length > 9 ? `${label.slice(0, 8)}…` : label}
          </text>
        </g>
      )}
    </svg>
  )
}

const ART: Record<ArtKind, ReactNode> = {
  biscuits: (
    <g>
      <path d="M18 40h84v42H18z" fill="#eea50b" />
      <path d="M18 40l-6 4 6 4-6 4 6 4-6 4 6 4-6 4 6 4-6 4 6 4V40zM102 40l6 4-6 4 6 4-6 4 6 4-6 4 6 4-6 4 6 4-6 4V40z" fill="#c97f06" />
      <rect x="26" y="52" width="68" height="20" rx="10" fill="#9a4d12" />
      <circle cx="34" cy="47" r="3" fill="#fff3c4" /><circle cx="86" cy="77" r="3" fill="#fff3c4" />
      <circle cx="44" cy="78" r="2" fill="#fff3c4" />
    </g>
  ),
  homecare: (
    <g>
      <path d="M30 30h60l4 74H26z" fill="#26904f" />
      <path d="M30 30h60v10H30z" fill="#176036" />
      <circle cx="60" cy="62" r="18" fill="#fffdf7" />
      <circle cx="60" cy="62" r="12" fill="#ade0bf" />
      <circle cx="48" cy="88" r="4" fill="#d5eedd" /><circle cx="70" cy="92" r="3" fill="#d5eedd" />
      <circle cx="80" cy="84" r="2.5" fill="#d5eedd" />
    </g>
  ),
  tea: (
    <g>
      <path d="M28 34l32-10 32 10v70H28z" fill="#a23b1d" />
      <path d="M28 34l32-10 32 10-32 10z" fill="#c4532c" />
      <rect x="36" y="54" width="48" height="34" rx="6" fill="#fff3c4" />
      <path d="M60 60c10 2 13 12 6 22-10-2-13-12-6-22z" fill="#26904f" />
      <path d="M60 60c1 8 3 15 6 22" stroke="#176036" strokeWidth="1.5" fill="none" />
    </g>
  ),
  noodles: (
    <g>
      <path d="M24 30c12-6 60-6 72 0l-4 74H28z" fill="#e5532d" />
      <path d="M24 30c12-6 60-6 72 0" fill="none" stroke="#b83a1a" strokeWidth="5" />
      <circle cx="60" cy="68" r="22" fill="#fff3c4" />
      <path d="M44 62q4-6 8 0t8 0 8 0 8 0M44 70q4-6 8 0t8 0 8 0 8 0M46 78q4-6 7 0t7 0 7 0 7 0" fill="none" stroke="#eea50b" strokeWidth="2.6" strokeLinecap="round" />
    </g>
  ),
  snacks: (
    <g>
      <path d="M30 26h60l-4 10 6 68H28l6-68z" fill="#fbc124" />
      <path d="M30 26h60l-4 10H34z" fill="#eea50b" />
      <path d="M48 58l12-10 12 10-4 18H52z" fill="#c97f06" />
      <path d="M54 62l6-5 6 5-2 9h-8z" fill="#ffe68a" />
      <circle cx="42" cy="90" r="3" fill="#fff3c4" /><circle cx="78" cy="88" r="3" fill="#fff3c4" />
    </g>
  ),
  staples: (
    <g>
      <path d="M32 28h56l8 76H24z" fill="#f4ead2" />
      <path d="M32 28h56l-2 8H34z" fill="#e9dab4" />
      <path d="M38 50h44v30H38z" fill="#176036" />
      <path d="M60 54c7 4 7 18 0 22-7-4-7-18 0-22z" fill="#fbc124" />
      <path d="M60 54v22" stroke="#c97f06" strokeWidth="1.5" />
    </g>
  ),
  personal: (
    <g>
      <rect x="44" y="22" width="32" height="12" rx="3" fill="#176036" />
      <path d="M38 34h44c4 0 6 4 6 8v56c0 4-3 6-6 6H38c-3 0-6-2-6-6V42c0-4 2-8 6-8z" fill="#7cca9a" />
      <rect x="40" y="54" width="40" height="28" rx="6" fill="#fffdf7" />
      <circle cx="60" cy="68" r="7" fill="#fbc124" />
    </g>
  ),
  beverages: (
    <g>
      <path d="M50 18h20v12l10 14v58c0 3-2 5-5 5H45c-3 0-5-2-5-5V44l10-14z" fill="#e5532d" />
      <rect x="50" y="14" width="20" height="8" rx="2" fill="#176036" />
      <rect x="40" y="58" width="40" height="26" fill="#fff3c4" />
      <path d="M48 76q6-12 12 0t12 0" fill="none" stroke="#26904f" strokeWidth="3" strokeLinecap="round" />
    </g>
  ),
  carton: (
    <g>
      <path d="M22 44l38-14 38 14v52l-38 12-38-12z" fill="#c9a26a" />
      <path d="M22 44l38 14 38-14M60 58v50" fill="none" stroke="#9c7741" strokeWidth="2" />
      <path d="M22 44l38-14 38 14-38 14z" fill="#e0bd85" />
      <rect x="30" y="66" width="20" height="12" rx="2" fill="#fffdf7" opacity="0.8" />
    </g>
  ),
}
