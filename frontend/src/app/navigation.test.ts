import { describe, expect, it } from 'vitest'
import { PUBLIC_NAV, publicNavItem } from '@/app/navigation'

describe('publicNavItem', () => {
  it('finds each public destination by path', () => {
    for (const item of PUBLIC_NAV) {
      expect(publicNavItem(item.to)).toBe(item)
    }
    expect(publicNavItem('/results').label).toBe('Results')
  })

  it('fails loudly for a path that is not in the public navigation', () => {
    expect(() => publicNavItem('/nowhere')).toThrow('Unknown public route: /nowhere')
  })
})
