import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchInput from '../SearchInput.vue'

describe('SearchInput', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('сообщает о новом значении только после паузы в наборе', async () => {
    const wrapper = mount(SearchInput, { props: { modelValue: '', delay: 300 } })
    const input = wrapper.find('input')

    await input.setValue('Ив')
    await input.setValue('Иван')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    vi.advanceTimersByTime(299)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    vi.advanceTimersByTime(1)
    expect(wrapper.emitted('update:modelValue')).toEqual([['Иван']])
  })

  it('обрезает пробелы по краям', async () => {
    const wrapper = mount(SearchInput, { props: { modelValue: '', delay: 100 } })

    await wrapper.find('input').setValue('  Петров ')
    vi.advanceTimersByTime(100)

    expect(wrapper.emitted('update:modelValue')).toEqual([['Петров']])
  })

  it('показывает значение, заданное снаружи', () => {
    const wrapper = mount(SearchInput, { props: { modelValue: 'Анна' } })

    expect(wrapper.find('input').element.value).toBe('Анна')
  })
})
