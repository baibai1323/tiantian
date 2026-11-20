<script setup>
// 首页：展示当前选中月份的支出总览、分类排行和最近几笔。
// 页面数据来自一个汇总接口，进入页面时加载一次，切换月份后重新加载。
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, ArrowRight } from '@element-plus/icons-vue'

import { api } from '../api'
import { store, formatMoney, formatDate, monthLabel, currentMonth } from '../state'

// router 是 Vue Router 的实例，用来在页面之间跳转（例如跳到账单页）。
// loading 控制骨架屏；summary 存后端返回的汇总数据；error 存加载失败信息。
const router = useRouter()
const loading = ref(true)
const summary = ref(null)
const error = ref('')

// 下面几个计算属性都从 summary 里取数，并给 null 一个安全的默认值，
// 这样模板在数据还没回来时也能正常渲染，不会因为读取 undefined 报错。
const total = computed(() => (summary.value ? summary.value.total_cents : 0))
const today = computed(() => (summary.value ? summary.value.today_cents : 0))
const count = computed(() => (summary.value ? summary.value.count : 0))
const recent = computed(() => (summary.value ? summary.value.recent : []))
const byL1 = computed(() => (summary.value ? summary.value.by_l1 : []))

// 取分类金额的最大值，作为排行条宽度的基准；至少为 1，避免除以 0。
const maxL1 = computed(() => Math.max(...byL1.value.map((x) => x.total_cents), 1))

// 判断当前选中的月份是不是本月。日均和「今天花了多少」只在本月才有意义。
const isThisMonth = computed(() => store.month === currentMonth())

/**
 * 计算某个月有多少天。
 * 参数 month 形如 "2026-11"。new Date(y, m, 0) 会得到「下个月的第 0 天」，
 * 也就是这个月的最后一天；闰年 2 月 29 天也由 Date 自动处理。
 */
function daysInMonth(month) {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m, 0).getDate()
}

// 日均支出 = 当月总支出 / 天数。口径（计算标准）分两种：
// 本月只除以已经过去的天数，历史月份除以整月天数，
// 这样本月不会因为未来还没到的日子把日均摊薄。
const avgPerDay = computed(() => {
  // 当月按已过天数算，历史月份按整月天数算
  const days = isThisMonth.value ? new Date().getDate() : daysInMonth(store.month)
  return Math.round(total.value / Math.max(days, 1))
})

/**
 * 加载首页汇总数据。
 * 按月请求后端，返回总额、今日支出、笔数、分类占比和最近几笔。
 * 请求期间打开骨架屏，失败时把错误信息显示在页面顶部。
 */
async function load() {
  loading.value = true
  error.value = ''
  try {
    summary.value = await api.summary(store.month)
  } catch (err) {
    error.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 跳转到账单页；带上一级分类 id 时，账单页会按该分类过滤。
function goBills(categoryL1) {
  router.push({ path: '/bills', query: categoryL1 ? { category_l1: categoryL1 } : {} })
}

// 组件挂载（第一次显示到页面上）后立即加载一次数据。
onMounted(load)
</script>

<template>
  <div class="home">
    <div v-if="error" class="error-box">{{ error }}</div>

    <section class="hero-card">
      <div class="hero-main">
        <div class="hero-label">{{ monthLabel(store.month) }}支出</div>
        <div class="hero-amount">
          <span class="hero-symbol">¥</span>
          <span class="hero-number">{{ formatMoney(total) }}</span>
        </div>
        <div class="hero-meta">
          <span v-if="isThisMonth">今天 <strong>¥{{ formatMoney(today) }}</strong></span>
          <span v-if="isThisMonth" class="dot">·</span>
          <span>共 <strong>{{ count }}</strong> 笔</span>
          <span class="dot">·</span>
          <span>日均 <strong>¥{{ formatMoney(avgPerDay) }}</strong></span>
        </div>
      </div>
      <div class="hero-side">
        <el-button class="hero-add" type="primary" size="large" :icon="Plus" @click="store.openDialog()">
          记一笔
        </el-button>
        <p class="hero-tip">每一笔都算数</p>
      </div>
    </section>

    <div class="home-grid">
      <section class="card">
        <div class="card-head">
          <h2>花在哪了</h2>
          <button class="link-btn" type="button" @click="goBills()">
            全部账单 <el-icon><ArrowRight /></el-icon>
          </button>
        </div>

        <el-skeleton v-if="loading" :rows="4" animated />
        <div v-else-if="!byL1.length" class="empty-box">
          <p class="empty-title">这个月还没有记录</p>
          <p class="empty-sub">点上面的「记一笔」，从一杯咖啡开始。</p>
        </div>
        <ul v-else class="rank-list">
          <li
            v-for="item in byL1.slice(0, 6)"
            :key="item.id"
            class="rank-item"
            @click="goBills(item.id)"
          >
            <span class="rank-name">{{ item.name }}</span>
            <span class="rank-bar">
              <i :style="{ width: `${Math.max((item.total_cents / maxL1) * 100, 3)}%` }"></i>
            </span>
            <span class="rank-value">¥{{ formatMoney(item.total_cents) }}</span>
            <span class="rank-pct">{{ item.percent.toFixed(0) }}%</span>
          </li>
        </ul>
      </section>

      <section class="card">
        <div class="card-head">
          <h2>最近几笔</h2>
          <button class="link-btn" type="button" @click="goBills()">
            查看全部 <el-icon><ArrowRight /></el-icon>
          </button>
        </div>

        <el-skeleton v-if="loading" :rows="4" animated />
        <div v-else-if="!recent.length" class="empty-box">
          <p class="empty-title">暂时没有记录</p>
          <p class="empty-sub">记下的每一笔，都会出现在这里。</p>
        </div>
        <ul v-else class="recent-list">
          <li v-for="item in recent" :key="item.id" class="recent-item" @click="store.openDialog(item)">
            <div class="recent-icon">{{ item.category_l2_name.slice(0, 1) }}</div>
            <div class="recent-body">
              <div class="recent-title">
                <span>{{ item.category_l2_name }}</span>
                <span class="muted small">{{ item.category_l1_name }}</span>
              </div>
              <div class="recent-sub">{{ item.note || formatDate(item.spent_on) }}</div>
            </div>
            <div class="recent-amount">¥{{ formatMoney(item.amount_cents) }}</div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
