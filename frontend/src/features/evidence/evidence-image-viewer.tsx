import { ImageOffIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { ErrorState, LoadingState } from '@/components/feedback/states'
import { Button } from '@/components/ui/button'
import { useEvidenceImage } from '@/features/evidence/api'
import type { EvidenceImage, ExtractedField } from '@/features/evidence/types'

type ViewerProps = {
  submissionId: string
  images: EvidenceImage[]
  /** Field whose OCR position to outline. Positions refer to the processed image. */
  highlight?: ExtractedField | null
}

function useObjectUrl(blob: Blob | undefined) {
  const url = useMemo(
    () => (blob && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob) : undefined),
    [blob],
  )
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url])
  return url
}

export function EvidenceImageViewer({ submissionId, images, highlight }: ViewerProps) {
  const processed = images.filter((image) => image.kind === 'processed').at(-1)
  const [variant, setVariant] = useState<'original' | 'processed'>('original')
  const showing = variant === 'processed' && processed ? 'processed' : 'original'
  const image = useEvidenceImage(submissionId, showing)
  const url = useObjectUrl(image.data?.blob)
  const box = showing === 'processed' && processed && highlight?.bbox ? highlight.bbox : null

  return (
    <div className="space-y-3">
      <div role="group" aria-label="Image version" className="flex gap-2">
        <Button
          size="sm"
          variant={showing === 'original' ? 'default' : 'outline'}
          aria-pressed={showing === 'original'}
          onClick={() => setVariant('original')}
        >
          Original (unaltered)
        </Button>
        <Button
          size="sm"
          variant={showing === 'processed' ? 'default' : 'outline'}
          aria-pressed={showing === 'processed'}
          disabled={!processed}
          onClick={() => setVariant('processed')}
        >
          Processed for OCR
        </Button>
      </div>
      <div className="relative overflow-hidden rounded-lg border bg-muted">
        {image.isPending ? (
          <LoadingState label="Loading image securely" />
        ) : image.isError ? (
          <ErrorState
            title="Image unavailable"
            message={
              image.error instanceof Error ? image.error.message : 'The image could not be loaded or failed verification.'
            }
          />
        ) : url ? (
          <div className="relative">
            <img
              src={url}
              alt={showing === 'original' ? 'Original result sheet photo' : 'Processed result sheet used for OCR'}
              className="block w-full"
            />
            {box && processed && (
              <div
                aria-hidden
                className="pointer-events-none absolute rounded-sm border-2 border-warning bg-warning/15"
                style={{
                  left: `${(box.left / processed.width) * 100}%`,
                  top: `${(box.top / processed.height) * 100}%`,
                  width: `${(box.width / processed.width) * 100}%`,
                  height: `${(box.height / processed.height) * 100}%`,
                }}
              />
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <ImageOffIcon className="size-4" aria-hidden /> No image
          </div>
        )}
      </div>
      {image.data?.sha256 && (
        <p className="text-xs break-all text-muted-foreground">
          Server-verified SHA-256 of this {showing} image: {image.data.sha256}
        </p>
      )}
      {box && <p className="text-xs text-muted-foreground">Outlined: where OCR read “{highlight?.label}”.</p>}
    </div>
  )
}
