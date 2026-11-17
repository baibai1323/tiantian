const BASE = ''

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (res.status === 204) return null
  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : `请求失败（${res.status}）`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

export const api = {
  health: () => request('/api/health'),
  categories: () => request('/api/categories'),
  manageCategories: () => request('/api/categories/manage'),
  createCategory: (body) => request('/api/categories', { method: 'POST', body: JSON.stringify(body) }),
  updateCategory: (id, body) => request(`/api/categories/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteCategory: (id) => request(`/api/categories/${id}`, { method: 'DELETE' }),

  expenses: (params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v)
    }
    return request(`/api/expenses?${qs.toString()}`)
  },
  createExpense: (body) => request('/api/expenses', { method: 'POST', body: JSON.stringify(body) }),
  updateExpense: (id, body) => request(`/api/expenses/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteExpense: (id) => request(`/api/expenses/${id}`, { method: 'DELETE' }),
  restoreExpense: (id) => request(`/api/expenses/${id}/restore`, { method: 'POST' }),
  purgeExpense: (id) => request(`/api/expenses/${id}/permanent`, { method: 'DELETE' }),
  trash: (params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v)
    }
    return request(`/api/expenses/trash?${qs.toString()}`)
  },
  emptyTrash: () => request('/api/expenses/trash', { method: 'DELETE' }),

  summary: (month) => request(`/api/stats/summary?month=${encodeURIComponent(month)}`),
  trend: (months = 6) => request(`/api/stats/trend?months=${months}`),
  exportUrl: (month) => `/api/export/csv?month=${encodeURIComponent(month)}`,
  importCsv: (content) => request('/api/import/csv', { method: 'POST', body: JSON.stringify({ content }) }),
}
