// 后端接口封装：页面组件不直接写 fetch，而是统一调用 api.xxx()。
// 集中在一处的好处是：请求头、JSON 解析、错误提示只需要维护一份。
// 这里的每个方法都返回 Promise，调用方用 await 或 .then() 取结果。
// BASE 是接口地址的前缀。开发时 Vite 代理会把 /api 转发到 8000 端口；
// 打包后前端由后端同源提供，所以留空字符串表示“用当前页面的地址”。
const BASE = ''

// request 是底层请求函数：拼接地址、解析响应体、把失败统一抛成 Error。
// path: 接口路径，例如 /api/expenses。
// options: fetch 的额外配置（method、body 等），默认为空对象。
async function request(path, options = {}) {
  // 默认按 JSON 发送；调用方传了 headers 就合并进来，后写的会覆盖先写的。
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  // 204 No Content 表示成功但没有响应体（删除接口常见），直接返回 null。
  if (res.status === 204) return null
  // 先按文本读出来再尝试解析 JSON：导入接口等场景可能返回纯文本。
  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      // 不是合法 JSON 就保留原始文本，交给调用方决定怎么展示。
      data = text
    }
  }
  // res.ok 在状态码 200-299 时为 true，其余都算失败。
  if (!res.ok) {
    // FastAPI 把错误说明放在 detail 字段里，优先用它；没有就拼一个通用提示。
    const detail = data && data.detail ? data.detail : `请求失败（${res.status}）`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

// api 对象按业务分组暴露方法，可以把它看成“后端接口的目录”。
export const api = {
  // 健康检查：App.vue 启动时调用它，顺便拿到后端版本号。
  health: () => request('/api/health'),
  // 分类下拉框用的精简列表；manage 给分类管理页用，会包含已停用的分类。
  categories: () => request('/api/categories'),
  manageCategories: () => request('/api/categories/manage'),
  // 分类的增、改（PATCH 表示只提交要改的字段）、删。
  createCategory: (body) => request('/api/categories', { method: 'POST', body: JSON.stringify(body) }),
  updateCategory: (id, body) => request(`/api/categories/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteCategory: (id) => request(`/api/categories/${id}`, { method: 'DELETE' }),

  // 支出列表：把筛选条件拼成查询串。值为空的键直接跳过，
  // 避免发出 ?keyword=undefined 这类让后端困惑的参数。
  expenses: (params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v)
    }
    return request(`/api/expenses?${qs.toString()}`)
  },
  // 新增、修改、删除账单，请求体统一用 JSON.stringify 转成字符串。
  createExpense: (body) => request('/api/expenses', { method: 'POST', body: JSON.stringify(body) }),
  updateExpense: (id, body) => request(`/api/expenses/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteExpense: (id) => request(`/api/expenses/${id}`, { method: 'DELETE' }),
  // 回收站是软删除：记录先挪进去，之后可以恢复，也可以彻底清除。
  restoreExpense: (id) => request(`/api/expenses/${id}/restore`, { method: 'POST' }),
  purgeExpense: (id) => request(`/api/expenses/${id}/permanent`, { method: 'DELETE' }),
  trash: (params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v)
    }
    return request(`/api/expenses/trash?${qs.toString()}`)
  },
  // 清空回收站：一次删掉里面所有记录，界面上会做二次确认。
  emptyTrash: () => request('/api/expenses/trash', { method: 'DELETE' }),

  // 统计：summary 按月汇总金额，trend 返回最近几个月（默认半年）的走势。
  summary: (month) => request(`/api/stats/summary?month=${encodeURIComponent(month)}`),
  trend: (months = 6) => request(`/api/stats/trend?months=${months}`),
  // 导出只返回下载地址、不真正发请求，浏览器打开该地址就会下载 CSV。
  exportUrl: (month) => `/api/export/csv?month=${encodeURIComponent(month)}`,
  // 导入：CSV 文本放在请求体里交给后端解析，前端不需要自己读文件格式。
  importCsv: (content) => request('/api/import/csv', { method: 'POST', body: JSON.stringify({ content }) }),
}
