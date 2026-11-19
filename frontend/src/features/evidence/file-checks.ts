/**
 * Early, client-side checks so users get immediate feedback. The server repeats
 * every check and is the only authority: these can be bypassed by a modified client.
 */

export const MAX_EVIDENCE_BYTES = 15 * 1024 * 1024
export const MIN_DIMENSION = 500

export const ACCEPTED_TYPES = {
  'image/jpeg': ['jpg', 'jpeg'],
  'image/png': ['png'],
  'image/webp': ['webp'],
} as const

export type AcceptedType = keyof typeof ACCEPTED_TYPES

export const ACCEPT_ATTRIBUTE = Object.keys(ACCEPTED_TYPES).join(',')

/** Identify the format from the file's first bytes rather than its name. */
export function sniffType(bytes: Uint8Array): AcceptedType | null {
  if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'image/jpeg'
  if ([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((value, index) => bytes[index] === value)) {
    return 'image/png'
  }
  const ascii = (start: number, end: number) => String.fromCharCode(...bytes.slice(start, end))
  if (ascii(0, 4) === 'RIFF' && ascii(8, 12) === 'WEBP') return 'image/webp'
  return null
}

export type FileCheck = { ok: true; type: AcceptedType } | { ok: false; message: string }

export function checkEvidenceFile(name: string, size: number, head: Uint8Array): FileCheck {
  if (size === 0) return { ok: false, message: 'The file is empty.' }
  if (size > MAX_EVIDENCE_BYTES) {
    return { ok: false, message: `The file is larger than ${MAX_EVIDENCE_BYTES / 1024 / 1024} MB.` }
  }
  const type = sniffType(head)
  if (!type) return { ok: false, message: 'Only JPEG, PNG and WebP photos are accepted.' }
  const extension = name.split('.').pop()?.toLowerCase() ?? ''
  if (extension && !(ACCEPTED_TYPES[type] as readonly string[]).includes(extension)) {
    return { ok: false, message: `The file name ends in .${extension} but the file is a ${type.split('/')[1]} image.` }
  }
  return { ok: true, type }
}

export type PreparedPhoto =
  | { ok: true; data: ArrayBuffer; type: AcceptedType; fileName: string; width: number | null; height: number | null }
  | { ok: false; message: string }

function fileNameFor(original: string, type: AcceptedType) {
  const stem = original.replace(/\.[^.]+$/, '').replace(/[^\w.-]+/g, '_').slice(0, 80)
  return `${stem || 'result-sheet'}.${ACCEPTED_TYPES[type][0]}`
}

/**
 * Phone cameras often hand back HEIC, or a file that cannot be read after the
 * input is reset. Read the bytes first, then keep JPEG, PNG and WebP as-is.
 * A photo the browser can decode but we cannot store (HEIC) is re-encoded as JPEG.
 */
export async function prepareEvidencePhoto(file: File): Promise<PreparedPhoto> {
  let data: ArrayBuffer
  try {
    data = await file.arrayBuffer()
  } catch {
    return { ok: false, message: 'The photo could not be read from the camera. Take it again.' }
  }
  if (data.byteLength === 0) return { ok: false, message: 'The photo is empty. Take it again.' }
  if (data.byteLength > MAX_EVIDENCE_BYTES) {
    return { ok: false, message: `The file is larger than ${MAX_EVIDENCE_BYTES / 1024 / 1024} MB.` }
  }

  let type = sniffType(new Uint8Array(data.slice(0, 16)))
  let width: number | null = null
  let height: number | null = null

  if (!type) {
    const converted = await transcodeToJpeg(data)
    if (!converted) {
      return {
        ok: false,
        message: 'Only JPEG, PNG and WebP photos are accepted. Take the photo again, or choose a JPEG.',
      }
    }
    data = converted.data
    type = 'image/jpeg'
    width = converted.width
    height = converted.height
    if (data.byteLength > MAX_EVIDENCE_BYTES) {
      return { ok: false, message: `The file is larger than ${MAX_EVIDENCE_BYTES / 1024 / 1024} MB.` }
    }
  } else {
    const size = await imageDimensions(new Blob([data], { type }))
    if (size) {
      width = size.width
      height = size.height
    }
  }

  if (width !== null && height !== null && Math.min(width, height) < MIN_DIMENSION) {
    return {
      ok: false,
      message: `The photo is too small (${width}×${height}). Take a closer, sharper photo of the whole sheet.`,
    }
  }
  return { ok: true, data, type, fileName: fileNameFor(file.name, type), width, height }
}

/** Draws a browser-decodable photo (including iPhone HEIC) onto a canvas and exports JPEG. */
async function transcodeToJpeg(data: ArrayBuffer): Promise<{ data: ArrayBuffer; width: number; height: number } | null> {
  if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return null
  let bitmap: ImageBitmap | null = null
  try {
    bitmap = await createImageBitmap(new Blob([data]))
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const context = canvas.getContext('2d')
    if (!context) return null
    context.drawImage(bitmap, 0, 0)
    const width = bitmap.width
    const height = bitmap.height
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    if (!blob) return null
    return { data: await blob.arrayBuffer(), width, height }
  } catch {
    return null
  } finally {
    bitmap?.close()
  }
}

export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/** Returns null when the browser cannot decode images off-screen (the server still checks). */
export async function imageDimensions(file: Blob): Promise<{ width: number; height: number } | null> {
  if (typeof createImageBitmap !== 'function') return null
  try {
    const bitmap = await createImageBitmap(file)
    const size = { width: bitmap.width, height: bitmap.height }
    bitmap.close()
    return size
  } catch {
    return null
  }
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
