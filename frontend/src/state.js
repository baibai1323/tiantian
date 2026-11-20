import { reactive } from 'vue'
import { api } from './api'

// 全局状态与格式化工具：多个页面共享的数据放在这里，避免一层层传参。
// store 用 reactive() 包了一层，任何组件读取它的属性都会自动跟随更新。
// currentMonth 返回当前月份字符串，格式固定为 YYYY-MM。
// 这个格式和 <el-date-picker type="month" value-format="YYYY-MM"> 的输出一致，
// 所以选中值可以直接当查询参数用。
export function currentMonth() {
  const d = new Date()
  // getMonth() 从 0 开始数（0 表示一月），所以要 +1；
  // padStart(2, '0') 把 7 补成 "07"，保证月份永远是两位。
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

// shiftMonth 在月份上前后移动若干个月，返回新的 YYYY-MM 字符串。
// month: 起始月份，如 "2025-01"；delta: 偏移量，-1 表示上个月，1 表示下个月。
export function shiftMonth(month, delta) {
  const [y, m] = month.split('-').map(Number)
  // 把日期固定成 1 号再算，避免 31 号遇到短月份时被“顺延”到再下一个月；
  // Date 会自动处理跨年（例如 1 月往前一个月得到上一年 12 月）。
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

// monthLabel 把 "2025-03" 变成适合展示的 "2025 年 3 月"。
// 用 Number(m) 去掉前导零，让“03 月”显示成“3 月”。
export function monthLabel(month) {
  const [y, m] = month.split('-')
  return `${y} 年 ${Number(m)} 月`
}

// formatMoney 把以“分”为单位的整数金额换算成“元”并格式化。
// 数据库用分存钱可以避免 0.1 + 0.2 这类小数误差，展示时才除以 100。
// toLocaleString 会加上千分位，并固定保留两位小数。
export function formatMoney(cents) {
  // Number(cents) || 0 处理 null、undefined 和空字符串，让它们显示成 0.00。
  const n = (Number(cents) || 0) / 100
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// formatDate 把后端返回的 "YYYY-MM-DD" 显示成 "M 月 D 日"。
// 没有日期（空字符串或 null）时返回空字符串，避免模板渲染出 "NaN 月"。
export function formatDate(dateStr) {
  if (!dateStr) return ''
  const [y, m, d] = dateStr.split('-')
  return `${Number(m)} 月 ${Number(d)} 日`
}

// store 是全局响应式状态对象，任何组件 import 后直接用即可。
export const store = reactive({
  // month 是当前查看的月份，顶部月份选择器直接和它双向绑定。
  month: currentMonth(),
  // version 显示在侧边栏底部，启动后由健康检查接口更新成后端真实版本。
  version: '0.5.1',
  // categories 是分类列表缓存，多个页面都要用，所以放在全局。
  categories: [],
  // categoriesLoaded 标记是否已经请求过分类，避免每次进页面都重复请求。
  categoriesLoaded: false,
  // dialogVisible 控制“记一笔”弹窗的显示与隐藏。
  dialogVisible: false,
  // editing 为 null 表示新增账单；有值时表示正在编辑哪一条记录。
  editing: null,
  // refreshToken 是“数据版本号”，每次数据变动就 +1。
  // 页面把它拼进 :key，key 一变 Vue 就会重新创建组件、重新拉数据。
  refreshToken: 0,

  // loadCategories 加载分类列表；已经加载过就直接返回缓存。
  // force 传 true 时强制重新请求（例如分类管理页改完分类之后）。
  async loadCategories(force = false) {
    if (this.categoriesLoaded && !force) return this.categories
    this.categories = await api.categories()
    this.categoriesLoaded = true
    return this.categories
  },

  // openDialog 打开记账弹窗。
  // expense 传 null（或不传）表示新增，传一条记录表示编辑它。
  openDialog(expense = null) {
    this.editing = expense
    this.dialogVisible = true
  },

  // closeDialog 关闭弹窗并清空编辑对象，下次打开才是干净的新增状态。
  closeDialog() {
    this.dialogVisible = false
    this.editing = null
  },

  // changed 在数据发生增删改后调用，递增版本号来通知各页面刷新。
  changed() {
    this.refreshToken += 1
  },
})

