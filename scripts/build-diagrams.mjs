#!/usr/bin/env node
// Builds the README diagrams in docs/images from code, so they can be regenerated
// when the system changes. Icons come from lucide (the icon set the app uses) and
// the logo comes from the app's own brand artwork.
//
//   node scripts/build-diagrams.mjs

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const ICONS = join(ROOT, 'frontend/node_modules/lucide-react/dist/esm/icons')
const OUT = join(ROOT, 'docs/images')

const C = {
  green: '#3bb75e',
  deep: '#1d6b3c',
  tint: '#eef8f1',
  tintLine: '#cfe9d7',
  navy: '#011b33',
  ink: '#0f2a44',
  muted: '#55677a',
  blueTint: '#f1f5fb',
  blueLine: '#d6e0ee',
  white: '#ffffff',
  amber: '#b7791f',
}
const FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

// ---------------------------------------------------------------- assets

const outline = readFileSync(join(ROOT, 'frontend/src/components/brand/nigeria-outline.ts'), 'utf8')
const LOGO_PATH = outline.match(/NIGERIA_LOGO_PATH =\s*'([^']+)'/)[1]
const RIDGES = [...outline.match(/FINGERPRINT_RIDGES = \[([\s\S]*?)\]/)[1].matchAll(/'([^']+)'/g)].map((m) => m[1])

const iconCache = new Map()
async function loadIcon(name) {
  if (!iconCache.has(name)) {
    const file = join(ICONS, `${name}.mjs`)
    const alias = readFileSync(file, 'utf8').match(/from '\.\/([\w-]+)\.mjs'/)
    const mod = await import(pathToFileURL(file).href)
    const data = mod.__iconData ?? (alias ? (await import(pathToFileURL(join(ICONS, `${alias[1]}.mjs`)).href)).__iconData : null)
    if (!data) throw new Error(`Icon not found: ${name}`)
    iconCache.set(name, data.node)
  }
  return iconCache.get(name)
}

function iconSvg(node, x, y, size, color, stroke = 2) {
  const scale = size / 24
  const parts = node
    .map(([tag, attrs]) => {
      const a = Object.entries(attrs)
        .filter(([k]) => k !== 'key')
        .map(([k, v]) => `${k}="${esc(v)}"`)
        .join(' ')
      return `<${tag} ${a}/>`
    })
    .join('')
  return `<g transform="translate(${x} ${y}) scale(${scale})" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round">${parts}</g>`
}

let clipId = 0
function logoMark(x, y, height) {
  const id = `nga${++clipId}`
  const s = height / 53
  return `<g transform="translate(${x} ${y}) scale(${s})">
    <defs><clipPath id="${id}"><path d="${LOGO_PATH}"/></clipPath></defs>
    <path d="${LOGO_PATH}" fill="${C.green}"/>
    <g clip-path="url(#${id})"><g transform="translate(16.2 10.4) scale(1.22)">
      <g fill="none" stroke="${C.navy}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${RIDGES.map((d) => `<path d="${d}"/>`).join('')}</g>
      <path d="M10.2 13.25 11.55 14.55 13.95 11.7" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
    </g></g>
  </g>`
}

// ---------------------------------------------------------------- primitives

const text = (x, y, s, { size = 14, weight = 400, color = C.ink, anchor = 'middle', style = '' } = {}) =>
  `<text x="${x}" y="${y}" font-family="${FONT}" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}"${style ? ` font-style="${style}"` : ''}>${esc(s)}</text>`

const lines = (x, y, arr, opts = {}, gap = (opts.size ?? 14) * 1.35) =>
  arr.map((s, i) => text(x, y + i * gap, s, opts)).join('')

const rect = (x, y, w, h, { fill = C.white, stroke = 'none', r = 10, sw = 1.2 } = {}) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`

function arrowDown(x, y1, y2, color = C.green) {
  return `<line x1="${x}" y1="${y1}" x2="${x}" y2="${y2 - 8}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M${x - 7} ${y2 - 10} L${x} ${y2} L${x + 7} ${y2 - 10}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`
}
function arrowRight(x1, x2, y, color = C.green) {
  return `<line x1="${x1}" y1="${y}" x2="${x2 - 8}" y2="${y}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
  <path d="M${x2 - 10} ${y - 7} L${x2} ${y} L${x2 - 10} ${y + 7}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`
}
function arrowBoth(x1, x2, y, color = C.green) {
  return `<line x1="${x1 + 8}" y1="${y}" x2="${x2 - 8}" y2="${y}" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M${x2 - 9} ${y - 6} L${x2} ${y} L${x2 - 9} ${y + 6}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M${x1 + 9} ${y - 6} L${x1} ${y} L${x1 + 9} ${y + 6}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`
}

function sectionLabel(x, y, w, h, label) {
  const parts = label.split('\n')
  const startY = y + h / 2 - ((parts.length - 1) * 19) / 2 + 6
  return rect(x, y, w, h, { fill: C.deep, r: 10 }) + lines(x + 18, startY, parts, { size: 16, weight: 700, color: C.white, anchor: 'start' }, 19)
}

async function header(width, title, subtitle) {
  const check = await loadIcon('check')
  return `
  ${logoMark(36, 30, 62)}
  ${text(118, 74, 'VoteTrace', { size: 42, weight: 800, color: C.navy, anchor: 'start' })}
  ${text(120, 100, 'Every Vote, Every Voice.', { size: 15, weight: 600, color: C.muted, anchor: 'start', style: 'italic' })}
  <line x1="470" y1="34" x2="470" y2="108" stroke="${C.tintLine}" stroke-width="2"/>
  ${rect(500, 26, width - 536, 88, { fill: C.deep, r: 14 })}
  ${iconSvg(check, width - 92, 48, 40, 'rgba(255,255,255,0.25)', 2.5)}
  ${text(500 + (width - 536) / 2, 66, title, { size: 32, weight: 800, color: C.white })}
  ${text(500 + (width - 536) / 2, 96, subtitle, { size: 16, weight: 500, color: '#d9f2e1', style: 'italic' })}`
}

function svgDoc(width, height, body, label) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}">
<rect width="${width}" height="${height}" fill="#ffffff"/>
${body}
</svg>
`
}

// ---------------------------------------------------------------- architecture

async function architecture() {
  const W = 1600
  const H = 1110
  const L = 32
  const LW = 206
  const X = L + LW + 44
  const CW = W - X - 32
  const out = [await header(W, 'System Design Architecture', 'Offline-first evidence and result verification for Nigerian polling units')]

  // Users and access channels
  const users = [
    ['users', 'Citizens', 'Web and installable app'],
    ['smartphone', 'Basic phones', 'USSD menu'],
    ['message-square-text', 'SMS', 'Text commands'],
    ['user-check', 'Observers and party agents', 'Result-sheet photos'],
    ['shield-check', 'Staff', 'Review, audit, admin'],
  ]
  let y = 146
  out.push(sectionLabel(L, y, LW, 104, 'Users and\naccess channels'))
  const uw = (CW - 4 * 16) / 5
  for (const [i, [icon, title, sub]] of users.entries()) {
    const x = X + i * (uw + 16)
    out.push(rect(x, y, uw, 104, { fill: C.blueTint, stroke: C.blueLine }))
    out.push(iconSvg(await loadIcon(icon), x + uw / 2 - 15, y + 14, 30, C.navy))
    out.push(text(x + uw / 2, y + 68, title, { size: 15, weight: 700 }))
    out.push(text(x + uw / 2, y + 88, sub, { size: 13, color: C.muted }))
    out.push(arrowDown(x + uw / 2, y + 108, y + 134))
  }

  // Frontend
  y = 284
  out.push(sectionLabel(L, y, LW, 104, 'Frontend\nReact 19 PWA'))
  out.push(rect(X, y, CW, 104, { fill: C.tint, stroke: C.tintLine }))
  const fe = [
    ['house', 'Public portal', 'Finder, updates, maps'],
    ['camera', 'Evidence capture', 'Camera, SHA-256, offline'],
    ['chart-column', 'Results dashboard', 'Live drill-down (SSE)'],
    ['triangle-alert', 'Incident reporting', 'Anonymous, offline'],
    ['layout-dashboard', 'Admin console', 'Review, audit, register'],
    ['phone', 'Phone access', 'USSD and SMS console'],
  ]
  const fw = CW / fe.length
  for (const [i, [icon, title, sub]] of fe.entries()) {
    const x = X + i * fw
    if (i) out.push(`<line x1="${x}" y1="${y + 18}" x2="${x}" y2="${y + 86}" stroke="${C.tintLine}" stroke-width="1.5"/>`)
    out.push(iconSvg(await loadIcon(icon), x + fw / 2 - 14, y + 14, 28, C.deep))
    out.push(text(x + fw / 2, y + 66, title, { size: 15, weight: 700 }))
    out.push(text(x + fw / 2, y + 86, sub, { size: 13, color: C.muted }))
  }
  out.push(arrowDown(X + CW * 0.4, y + 108, y + 140))

  // Backend, security, external
  y = 428
  const BH = 300
  const extW = 252
  const BX = X
  const BW = CW - extW - 56
  // Security panel in the label column
  out.push(rect(L, y, LW, BH, { fill: C.tint, stroke: C.tintLine }))
  out.push(rect(L, y, LW, 44, { fill: C.deep, r: 10 }))
  out.push(text(L + 18, y + 28, 'Security', { size: 16, weight: 700, color: C.white, anchor: 'start' }))
  out.push(iconSvg(await loadIcon('lock'), L + LW - 40, y + 10, 24, C.white))
  const security = [
    'JWT sessions and roles',
    'scrypt password hashing',
    'Rate limiting',
    'HMAC-signed callbacks',
    'Hash-chained audit log',
    'Hashed phone numbers',
    'PII masking in reports',
    'HSTS and strict CORS',
  ]
  const checkIcon = await loadIcon('circle-check')
  for (const [i, s] of security.entries()) {
    const yy = y + 66 + i * 28
    out.push(iconSvg(checkIcon, L + 14, yy - 13, 16, C.green, 2.4))
    out.push(text(L + 40, yy, s, { size: 13, anchor: 'start' }))
  }
  out.push(arrowBoth(L + LW + 2, BX - 2, y + BH / 2))

  out.push(rect(BX, y, BW, BH, { fill: C.blueTint, stroke: C.blueLine }))
  out.push(rect(BX, y, BW, 50, { fill: C.navy, r: 10 }))
  out.push(text(BX + BW / 2, y + 32, 'VoteTrace API  ·  FastAPI  /api/v1', { size: 19, weight: 700, color: C.white }))
  const services = [
    ['scan-text', 'Evidence engine', ['Content file checks', 'SHA-256 fingerprint', 'OpenCV clean-up', 'OCR with confidence']],
    ['calculator', 'Verification', ['Arithmetic rules', 'Compare submissions', 'Two approvals needed', 'No self-review']],
    ['sparkles', 'VoteTrace AI', ['Isolation Forest', 'Discrepancy alerts', 'OCR uncertainty', 'Explains every alert']],
    ['network', 'Aggregation', ['PU > Ward > LGA', 'State > National', 'Units counted once', 'Live events (SSE)']],
    ['siren', 'Incidents', ['Rule-based triage', 'Duplicate detection', 'Review workflow', 'Public summary']],
    ['radio-tower', 'Phone channels', ['USSD menu engine', 'SMS commands', 'Read-only by design', "Africa's Talking"]],
  ]
  const sgap = 12
  const sw = (BW - 32 - sgap * (services.length - 1)) / services.length
  for (const [i, [icon, title, bullets]] of services.entries()) {
    const x = BX + 16 + i * (sw + sgap)
    const sy = y + 66
    out.push(rect(x, sy, sw, BH - 82, { fill: C.white, stroke: C.blueLine, r: 8 }))
    out.push(iconSvg(await loadIcon(icon), x + sw / 2 - 15, sy + 16, 30, C.navy))
    out.push(text(x + sw / 2, sy + 72, title, { size: 15, weight: 700 }))
    out.push(`<line x1="${x + 16}" y1="${sy + 86}" x2="${x + sw - 16}" y2="${sy + 86}" stroke="${C.blueLine}"/>`)
    for (const [j, b] of bullets.entries()) {
      const by = sy + 112 + j * 26
      out.push(`<circle cx="${x + 14}" cy="${by - 4}" r="2.6" fill="${C.green}"/>`)
      out.push(text(x + 23, by, b, { size: 12, anchor: 'start', color: C.ink }))
    }
  }

  const EX = BX + BW + 56
  out.push(arrowBoth(BX + BW + 2, EX - 2, y + BH / 2))
  out.push(rect(EX, y, extW, BH, { fill: C.blueTint, stroke: C.blueLine }))
  out.push(text(EX + extW / 2, y + 32, 'External integrations', { size: 16, weight: 700, color: C.navy }))
  const ext = [
    ['file-spreadsheet', 'INEC register file', 'CSV import by admins'],
    ['radio-tower', "Africa's Talking", 'USSD and SMS gateway'],
    ['cloud', 'Supabase', 'Postgres, Auth, Storage'],
    ['map-pin', 'OpenStreetMap', 'Leaflet map tiles'],
  ]
  for (const [i, [icon, title, sub]] of ext.entries()) {
    const yy = y + 56 + i * 60
    out.push(iconSvg(await loadIcon(icon), EX + 16, yy + 4, 26, C.deep))
    out.push(text(EX + 54, yy + 16, title, { size: 14, weight: 700, anchor: 'start' }))
    out.push(text(EX + 54, yy + 35, sub, { size: 12, color: C.muted, anchor: 'start' }))
  }
  out.push(arrowDown(BX + BW / 2, y + BH + 4, y + BH + 34))

  // Data layer
  y = 766
  out.push(sectionLabel(L, y, LW, 96, 'Data layer'))
  out.push(rect(X, y, CW, 96, { fill: C.tint, stroke: C.tintLine }))
  const data = [
    ['database', 'PostgreSQL + PostGIS', 'Supabase, row-level security'],
    ['hard-drive', 'Private evidence store', 'Content-addressed originals'],
    ['table', 'Derived result tables', 'Same-transaction refresh'],
    ['wifi-off', 'IndexedDB (Dexie)', 'Offline drafts and cache'],
    ['file-text', 'SQLite', 'Local development and preview'],
  ]
  const dw = CW / data.length
  for (const [i, [icon, title, sub]] of data.entries()) {
    const x = X + i * dw
    if (i) out.push(`<line x1="${x}" y1="${y + 16}" x2="${x}" y2="${y + 80}" stroke="${C.tintLine}" stroke-width="1.5"/>`)
    out.push(iconSvg(await loadIcon(icon), x + 20, y + 30, 34, C.deep))
    out.push(text(x + 66, y + 44, title, { size: 15, weight: 700, anchor: 'start' }))
    out.push(text(x + 66, y + 64, sub, { size: 12.5, color: C.muted, anchor: 'start' }))
  }

  // Engineering and tooling
  y = 882
  out.push(sectionLabel(L, y, LW, 84, 'Engineering\nand tooling'))
  out.push(rect(X, y, CW, 84, { fill: C.blueTint, stroke: C.blueLine }))
  const tools = [
    ['zap', 'Vite + Workbox', 'Build and offline shell'],
    ['git-branch', 'Alembic', '6 schema migrations'],
    ['server', 'Uvicorn', 'ASGI server'],
    ['flask-conical', 'Pytest · Vitest', 'Playwright end to end'],
    ['shield-check', 'Ruff · ESLint', 'Strict TypeScript'],
    ['book-open', 'Markdown docs', 'Mermaid and SVG diagrams'],
  ]
  const tw = CW / tools.length
  for (const [i, [icon, title, sub]] of tools.entries()) {
    const x = X + i * tw
    if (i) out.push(`<line x1="${x}" y1="${y + 16}" x2="${x}" y2="${y + 68}" stroke="${C.blueLine}" stroke-width="1.5"/>`)
    out.push(iconSvg(await loadIcon(icon), x + 16, y + 28, 28, C.navy))
    out.push(text(x + 54, y + 38, title, { size: 14, weight: 700, anchor: 'start' }))
    out.push(text(x + 54, y + 57, sub, { size: 12, color: C.muted, anchor: 'start' }))
  }

  // Outcomes
  y = 986
  out.push(sectionLabel(L, y, LW, 84, 'Key outcomes'))
  out.push(rect(X, y, CW, 84, { fill: C.tint, stroke: C.tintLine }))
  const outcomes = ['Traceable results', 'Verifiable evidence', 'Live updates', 'Works offline', 'Basic-phone access']
  const ow = CW / outcomes.length
  for (const [i, s] of outcomes.entries()) {
    const x = X + i * ow
    if (i) out.push(`<line x1="${x}" y1="${y + 20}" x2="${x}" y2="${y + 64}" stroke="${C.tintLine}" stroke-width="1.5"/>`)
    out.push(`<circle cx="${x + 40}" cy="${y + 42}" r="15" fill="${C.deep}"/>`)
    out.push(iconSvg(await loadIcon('check'), x + 31, y + 33, 18, C.white, 3))
    out.push(text(x + 66, y + 48, s, { size: 17, weight: 700, anchor: 'start' }))
  }

  out.push(text(W / 2, H - 14, 'Only components that exist in this repository are shown. Figures are independent civic verification, not INEC declarations.', { size: 12, color: C.muted }))
  return svgDoc(W, H, out.join('\n'), 'VoteTrace system design architecture')
}

// ---------------------------------------------------------------- election process

async function process() {
  const W = 1600
  const H = 1010
  const out = [await header(W, "How VoteTrace fits Nigeria's election process", 'An independent check on every polling-unit result sheet')]

  // Official process
  const official = [
    ['users', 'Voting at the polling unit', ['Citizens cast their votes.']],
    ['file-text', 'Result sheet (Form EC8A)', ['Counted, recorded and', 'pasted at the unit.']],
    ['landmark', 'Collation', ['Ward, LGA and state', 'collation centres.']],
    ['trophy', 'Declaration', ['INEC declares the', 'official result.']],
  ]
  const top = 150
  const cw = 330
  const gap = (W - 64 - cw * 4) / 3
  for (const [i, [icon, title, body]] of official.entries()) {
    const x = 32 + i * (cw + gap)
    out.push(rect(x, top, cw, 170, { fill: C.blueTint, stroke: C.blueLine, r: 14 }))
    out.push(iconSvg(await loadIcon(icon), x + cw / 2 - 22, top + 20, 44, C.navy))
    out.push(text(x + cw / 2, top + 98, title, { size: 19, weight: 800, color: C.navy }))
    out.push(lines(x + cw / 2, top + 124, body, { size: 14.5, color: C.muted }, 20))
    if (i < 3) out.push(arrowRight(x + cw + 14, x + cw + gap - 14, top + 85))
  }
  out.push(text(32, top - 12, 'The official process (run by INEC)', { size: 14, weight: 700, color: C.muted, anchor: 'start' }))

  const sheetX = 32 + cw + gap + cw / 2
  out.push(arrowDown(sheetX, top + 174, 384))
  out.push(text(sheetX + 14, top + 210, 'Observers photograph the sheet', { size: 13, weight: 600, color: C.deep, anchor: 'start' }))

  // Platform
  const PX = 32
  const PY = 400
  const PW = 1196
  const PH = 330
  out.push(rect(PX, PY, PW, PH, { fill: C.tint, stroke: C.green, r: 16, sw: 2 }))
  out.push(rect(PX + PW / 2 - 140, PY - 22, 280, 44, { fill: C.deep, r: 22 }))
  out.push(text(PX + PW / 2, PY + 8, 'VoteTrace platform', { size: 21, weight: 800, color: C.white }))
  const steps = [
    ['camera', 'Evidence capture', ['Accredited observers', 'photograph the sheet,', 'even offline.']],
    ['scan-text', 'OCR and AI', ['OpenCV cleans the image,', 'OCR drafts the figures,', 'AI flags anomalies.']],
    ['shield-check', 'Validation', ['Arithmetic rules,', 'SHA-256 integrity and', 'cross-checks.']],
    ['users', 'Human review', ['Two different reviewers', 'must approve. Nobody', 'reviews their own.']],
    ['database', 'Audit registry', ['Hash-chained log and', 'append-only history', 'for every change.']],
  ]
  const sw = 214
  const sgap = (PW - 40 - sw * 5) / 4
  for (const [i, [icon, title, body]] of steps.entries()) {
    const x = PX + 20 + i * (sw + sgap)
    const y = PY + 44
    out.push(rect(x, y, sw, 262, { fill: C.white, stroke: C.tintLine, r: 12 }))
    out.push(`<circle cx="${x + sw / 2}" cy="${y + 30}" r="17" fill="${C.deep}"/>`)
    out.push(text(x + sw / 2, y + 36, String(i + 1), { size: 16, weight: 800, color: C.white }))
    out.push(text(x + sw / 2, y + 78, title, { size: 18, weight: 800, color: C.navy }))
    out.push(iconSvg(await loadIcon(icon), x + sw / 2 - 26, y + 98, 52, C.navy, 1.8))
    out.push(lines(x + sw / 2, y + 190, body, { size: 13.5, color: C.ink }, 19))
    if (i < 4) out.push(arrowRight(x + sw + 4, x + sw + sgap - 4, y + 131))
  }

  // Public access panel
  const AX = 1262
  const AW = W - 32 - AX
  out.push(arrowRight(PX + PW + 6, AX - 6, PY + PH / 2))
  out.push(rect(AX, PY - 20, AW, PH + 40, { fill: C.white, stroke: C.tintLine, r: 14 }))
  out.push(rect(AX, PY - 20, AW, 52, { fill: C.tint, r: 14 }))
  out.push(text(AX + AW / 2, PY + 13, 'Open, accessible results', { size: 17, weight: 800, color: C.navy }))
  const access = [
    ['monitor', 'Results dashboard', 'Unit > Ward > LGA > State'],
    ['smartphone', 'USSD and SMS', 'For basic phones'],
    ['map-pin', 'Finder and updates', 'Polling units and notices'],
    ['triangle-alert', 'Incident summary', 'Reviewed reports only'],
  ]
  for (const [i, [icon, title, sub]] of access.entries()) {
    const y = PY + 50 + i * 68
    out.push(rect(AX + 12, y, AW - 24, 58, { fill: C.blueTint, r: 10 }))
    out.push(iconSvg(await loadIcon(icon), AX + 24, y + 15, 28, C.navy))
    out.push(text(AX + 64, y + 26, title, { size: 14.5, weight: 700, anchor: 'start' }))
    out.push(text(AX + 64, y + 45, sub, { size: 12, color: C.muted, anchor: 'start' }))
  }

  // Bottom band
  const BY = 790
  out.push(rect(32, BY, W - 64, 170, { fill: C.tint, stroke: C.tintLine, r: 16 }))
  out.push(`<circle cx="104" cy="${BY + 85}" r="38" fill="${C.deep}"/>`)
  out.push(iconSvg(await loadIcon('check'), 82, BY + 63, 44, C.white, 3))
  out.push(text(166, BY + 62, 'Every polling-unit result, traceable to its evidence', { size: 26, weight: 800, color: C.navy, anchor: 'start' }))
  out.push(
    lines(
      166,
      BY + 98,
      [
        'VoteTrace makes each result sheet checkable: the original photo, its fingerprint, the figures read from it,',
        'every correction and every reviewer decision. Discrepancies become visible, and nothing is verified automatically.',
      ],
      { size: 15.5, color: C.ink, anchor: 'start' },
      24,
    ),
  )
  out.push(`<line x1="1210" y1="${BY + 30}" x2="1210" y2="${BY + 140}" stroke="${C.tintLine}" stroke-width="2"/>`)
  out.push(lines(1240, BY + 70, ['Independent civic check.', 'Official results are', 'declared by INEC.'], { size: 16, weight: 600, color: C.deep, anchor: 'start', style: 'italic' }, 24))

  return svgDoc(W, H, out.join('\n'), "How VoteTrace fits Nigeria's election process")
}

mkdirSync(OUT, { recursive: true })
writeFileSync(join(OUT, 'architecture.svg'), await architecture())
writeFileSync(join(OUT, 'election-process.svg'), await process())
console.log('Wrote docs/images/architecture.svg and docs/images/election-process.svg')
