<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { HomeFilled, Tickets, TrendCharts, Setting, Plus } from '@element-plus/icons-vue'

import ExpenseDialog from './components/ExpenseDialog.vue'
import { api } from './api'
import { store, monthLabel } from './state'

const route = useRoute()

const navItems = [
  { path: '/', label: '首页', icon: HomeFilled },
  { path: '/bills', label: '账单', icon: Tickets },
  { path: '/stats', label: '统计', icon: TrendCharts },
  { path: '/settings', label: '设置', icon: Setting },
]

const pageTitle = computed(() => route.meta.title || '天天记账')
const todayText = computed(() => {
  const d = new Date()
  const weeks = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 星期${weeks[d.getDay()]}`
})

onMounted(() => {
  store.loadCategories().catch(() => {})
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
          active-class="is-active"
          :exact-active-class="item.path === '/' ? 'is-active' : ''"
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
