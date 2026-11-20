import { describe, expect, it } from 'vitest'
import {
  currentMonth,
  formatDate,
  formatMoney,
  monthLabel,
  shiftMonth,
} from '../state'

// 这些用例只覆盖 frontend/src/state.js 里的纯函数：
// 它们不碰网络、不碰 DOM，是前端最容易出错也最容易测的一部分。
// 断言一律写具体值，不写 toBeTruthy——那样只能证明「有东西」，证明不了「对」。

describe('formatMoney 分转元', () => {
  it('把 2800 分显示成 28.00 元', () => {
    expect(formatMoney(2800)).toBe('28.00')
  })

  it('5 分显示成 0.05 元，不会丢前导零', () => {
    expect(formatMoney(5)).toBe('0.05')
  })

  it('null 和空字符串都按 0 处理', () => {
    expect(formatMoney(null)).toBe('0.00')
    expect(formatMoney('')).toBe('0.00')
  })

  it('大额金额带千分位', () => {
    expect(formatMoney(123456789)).toBe('1,234,567.89')
  })
})

describe('shiftMonth 前后翻月', () => {
  it('1 月往前一个月是上一年 12 月', () => {
    expect(shiftMonth('2025-01', -1)).toBe('2024-12')
  })

  it('12 月往后一个月是下一年 1 月', () => {
    expect(shiftMonth('2025-12', 1)).toBe('2026-01')
  })

  it('月份始终补零到两位', () => {
    expect(shiftMonth('2025-10', 1)).toBe('2025-11')
  })
})

describe('monthLabel 展示文案', () => {
  it('去掉月份的前导零', () => {
    expect(monthLabel('2025-03')).toBe('2025 年 3 月')
  })
})

describe('formatDate 日期展示', () => {
  it('把 2026-01-05 显示成 1 月 5 日', () => {
    expect(formatDate('2026-01-05')).toBe('1 月 5 日')
  })

  it('空值返回空字符串，而不是 NaN 月', () => {
    expect(formatDate('')).toBe('')
    expect(formatDate(null)).toBe('')
  })
})

describe('currentMonth 当前月份格式', () => {
  it('总是 YYYY-MM 的两位月份格式', () => {
    expect(currentMonth()).toMatch(/^\d{4}-\d{2}$/)
  })
})
