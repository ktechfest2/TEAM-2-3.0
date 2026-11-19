import 'fake-indexeddb/auto'
import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Lazy route chunks compile on first import; under a parallel run that can exceed the 1s default.
configure({ asyncUtilTimeout: 8_000 })

afterEach(() => {
  cleanup()
})
