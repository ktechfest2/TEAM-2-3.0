import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { OFFERED_LOCALES } from '@/i18n/languages'
import { installMockApi } from '@/test/mock-api'
import { renderRoute } from '@/test/render'

afterEach(() => {
  window.localStorage.clear()
})

describe('language switcher', () => {
  it('offers the translated languages and switches the page copy', async () => {
    const user = userEvent.setup()
    installMockApi()
    renderRoute('/')

    const dropdown = await screen.findByRole('combobox', { name: 'Choose language' })
    const options = screen.getAllByRole('option')
    expect(options.map((option) => option.getAttribute('value'))).toEqual([...OFFERED_LOCALES])
    expect(screen.queryByRole('option', { name: /Tiv/ })).not.toBeInTheDocument()

    await user.selectOptions(dropdown, 'yo')
    expect(dropdown).toHaveValue('yo')
    expect(screen.getAllByRole('link', { name: 'Wọlé fún òṣìṣẹ́' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Àbájade ibi ìdìbò, pẹ̀lú ẹ̀rí tí a lè fìdí rẹ̀ múlẹ̀.',
    )
  })
})
