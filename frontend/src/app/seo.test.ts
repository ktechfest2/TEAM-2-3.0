import { describe, expect, it } from 'vitest'
import { metaForSegment, withSite } from '@/app/seo'

const INDEXED = ['', 'polling-units', 'results', 'verification', 'updates', 'report-incident', 'incidents', 'phone-access']
const HIDDEN = ['evidence', 'admin', 'account', 'not-a-page']

describe('route metadata', () => {
  it('indexes the public sections and hides the rest', () => {
    for (const segment of INDEXED) expect(metaForSegment(segment).index).toBe(true)
    for (const segment of HIDDEN) expect(metaForSegment(segment).index).toBe(false)
  })

  it('gives every indexed section its own title and description', () => {
    const titles = INDEXED.map((segment) => metaForSegment(segment).title)
    expect(new Set(titles).size).toBe(titles.length)
    for (const segment of INDEXED) {
      expect(metaForSegment(segment).description.length).toBeGreaterThan(40)
    }
  })

  it('adds the site name once', () => {
    expect(withSite('Results')).toBe('Results | VoteTrace')
    expect(withSite('VoteTrace | Every Vote, Every Voice')).toBe('VoteTrace | Every Vote, Every Voice')
  })
})
