import { reactive } from 'vue'
import { api } from './api'

export function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function shiftMonth(month, delta) {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function monthLabel(month) {
  const [y, m] = month.split('-')
  return `${y} 年 ${Number(m)} 月`
}

export function formatMoney(cents) {
  const n = (Number(cents) || 0) / 100
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatDate(dateStr) {
  if (!dateStr) return ''
  const [y, m, d] = dateStr.split('-')
  return `${Number(m)} 月 ${Number(d)} 日`
}

export const store = reactive({
  month: currentMonth(),
  version: '0.5.1',
  categories: [],
  categoriesLoaded: false,
  dialogVisible: false,
  editing: null,
  refreshToken: 0,

  async loadCategories(force = false) {
    if (this.categoriesLoaded && !force) return this.categories
    this.categories = await api.categories()
    this.categoriesLoaded = true
    return this.categories
  },

  openDialog(expense = null) {
    this.editing = expense
    this.dialogVisible = true
  },

  closeDialog() {
    this.dialogVisible = false
    this.editing = null
  },

  changed() {
    this.refreshToken += 1
  },
})

