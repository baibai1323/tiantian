<script setup>
// <script setup> 是 Vue 3 的语法糖：这里声明的变量和函数可以直接在 <template> 里使用，
// 不需要再写 export default 和 setup() 返回值。
// computed 用来定义“跟着依赖自动更新的值”，onMounted 是组件挂载后的生命周期钩子。
import { computed, onMounted } from 'vue'
// useRoute 用来读取当前路由信息（路径、meta 等）。
import { useRoute } from 'vue-router'
// 侧边栏和底部导航用到的图标组件。
import { HomeFilled, Tickets, TrendCharts, Setting, Plus, Delete } from '@element-plus/icons-vue'

// 记账弹窗组件：整个应用只放一个，通过 store.dialogVisible 控制显示。
import ExpenseDialog from './components/ExpenseDialog.vue'
// api 用于健康检查；store 是全局状态，monthLabel 负责把月份显示成中文。
import { api } from './api'
import { store, monthLabel } from './state'

// 当前路由对象，下面用它计算标题和导航高亮。
const route = useRoute()

// 导航配置：侧边栏和手机底部标签栏共用这份数据，改一处两边同时生效。
const navItems = [
  { path: '/', label: '首页', icon: HomeFilled },
  { path: '/bills', label: '账单', icon: Tickets },
  { path: '/trash', label: '回收站', icon: Delete },
  { path: '/stats', label: '统计', icon: TrendCharts },
  { path: '/settings', label: '设置', icon: Setting },
]

// 顶部标题优先用路由 meta.title，没有配置就退回应用名。
const pageTitle = computed(() => route.meta.title || '天天记账')
// isNavActive 判断某个导航项当前是否处于选中状态。
// path: 导航项对应的路由路径。
function isNavActive(path) {
  // 首页必须精确匹配，否则任何路径都会被算作首页；
  // 其他页面用 startsWith，是为了让 /settings/categories 也能点亮“设置”。
  return path === '/' ? route.path === '/' : route.path === path || route.path.startsWith(`${path}/`)
}
// 顶部显示的“今天”：格式为“X 月 X 日 星期X”。
const todayText = computed(() => {
  const d = new Date()
  // weeks 把 getDay() 返回的 0-6 映射成中文星期，其中 0 表示星期日。
  const weeks = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 星期${weeks[d.getDay()]}`
})

// 组件挂载完成后执行一次：预加载分类列表，并询问后端版本号。
onMounted(() => {
  // 用 .catch(() => {}) 静默忽略失败：分类加载失败时首页仍能显示，不弹错误打断用户。
  store.loadCategories().catch(() => {})
  // 健康检查成功就把后端版本号写进 store，显示在侧边栏底部。
  api.health().then((h) => { store.version = h.version }).catch(() => {})
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">天</div>
        <div class="brand-text">
          <strong>天天记账</strong>
          <span>认真花，明白记</span>
        </div>
      </div>

      <nav class="side-nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ 'is-active': isNavActive(item.path) }"
        >
          <el-icon :size="19"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <el-button class="side-add" type="primary" size="large" :icon="Plus" @click="store.openDialog()">
        记一笔
      </el-button>

      <div class="side-foot">
        <span>{{ monthLabel(store.month) }}</span>
        <span class="muted">v{{ store.version }}</span>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="topbar-left">
          <span class="mobile-brand">天天记账</span>
          <h1>{{ pageTitle }}</h1>
          <span class="today hide-sm">{{ todayText }}</span>
        </div>
        <el-date-picker
          v-model="store.month"
          type="month"
          format="YYYY 年 MM 月"
          value-format="YYYY-MM"
          :clearable="false"
          class="month-picker"
        />
      </header>

      <section class="page">
        <router-view :key="`${store.month}-${store.refreshToken}`" />
      </section>
    </main>

    <nav class="tabbar">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="tab-item"
        active-class="is-active"
        :exact-active-class="item.path === '/' ? 'is-active' : ''"
      >
        <el-icon :size="21"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <button class="mobile-fab" type="button" aria-label="记一笔" @click="store.openDialog()">
      <el-icon :size="24"><Plus /></el-icon>
    </button>

    <ExpenseDialog />
  </div>
</template>
