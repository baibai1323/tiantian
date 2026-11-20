<script setup>
// 统计页：用图表展示当前月份的一级分类占比、近 6 个月趋势和二级分类排行。
// 数据来自两个接口：月度汇总和最近 6 个月的每月合计。
// 页面是只读的，切换月份由顶部导航控制，进入页面时按当前月份查询。
import { computed, onMounted, ref } from 'vue'

import { api } from '../api'
import { store, formatMoney, monthLabel } from '../state'

// loading 控制骨架屏；summary 存月度汇总；trend 存近 6 个月数组；error 存错误信息。
const loading = ref(true)
const summary = ref(null)
const trend = ref([])
const error = ref('')

// 图表配色盘。分类数量不固定，用下标对颜色总数取余（index % length），
// 颜色用完一轮后从头循环，保证每个分类都有颜色且相邻颜色不重复。
const palette = [
  '#f59e0b',
  '#fb923c',
  '#f87171',
  '#a78bfa',
  '#60a5fa',
  '#34d399',
  '#facc15',
  '#f472b6',
  '#22d3ee',
  '#94a3b8',
]

// 从汇总数据里安全取数：summary 还没加载时给 0，模板不会读到 undefined。
const total = computed(() => (summary.value ? summary.value.total_cents : 0))
const count = computed(() => (summary.value ? summary.value.count : 0))
const byL1 = computed(() => (summary.value ? summary.value.by_l1 : []))
const byL2 = computed(() => (summary.value ? summary.value.by_l2 : []))

// 日均口径与首页一致：本月除以已过天数，历史月份除以整月天数。
// 先拼出当前月份的 "YYYY-MM" 字符串，再和 store.month 比较，判断是否本月。
// 历史月份用 new Date(年, 月, 0).getDate() 取该月最后一天，也就是总天数。
const avgPerDay = computed(() => {
  const now = new Date()
  const isThisMonth = store.month === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const days = isThisMonth ? now.getDate() : new Date(Number(store.month.slice(0, 4)), Number(store.month.slice(5, 7)), 0).getDate()
  return Math.round(total.value / Math.max(days, 1))
})

// 趋势图的高度基准：取 6 个月里的最大值，至少为 1，避免除以 0。
// trendTotal 是这 6 个月的合计，显示在卡片右上角。
const trendMax = computed(() => Math.max(...trend.value.map((x) => x.total_cents), 1))
const trendTotal = computed(() => trend.value.reduce((acc, x) => acc + x.total_cents, 0))

/**
 * 取第 index 个分类对应的颜色。
 * 取余是为了让下标超出配色盘长度时从头循环，不会越界拿到 undefined。
 */
function colorAt(index) {
  return palette[index % palette.length]
}

/**
 * 把 "2026-11" 这样的月份字符串转成「11 月」显示。
 * slice(5, 7) 取的是第 6、7 个字符，即月份部分；Number() 去掉前导零。
 */
function trendLabel(month) {
  return `${Number(month.slice(5, 7))} 月`
}

/**
 * 同时加载月度汇总和近 6 个月趋势。
 * Promise.all 让两个请求并行发出，等两个都成功后再一起渲染，比串行更快；
 * 任意一个失败都会进入 catch，把错误显示在页面顶部。
 */
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [summaryData, trendData] = await Promise.all([api.summary(store.month), api.trend(6)])
    summary.value = summaryData
    trend.value = trendData
  } catch (err) {
    error.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 页面首次显示时加载数据。统计页只读，不需要监听其他变化。
onMounted(load)
</script>

<template>
  <div class="stats">
    <div v-if="error" class="error-box">{{ error }}</div>

    <section class="stat-tiles">
      <div class="stat-tile">
        <span class="stat-label">{{ monthLabel(store.month) }}支出</span>
        <span class="stat-value">¥{{ formatMoney(total) }}</span>
      </div>
      <div class="stat-tile">
        <span class="stat-label">记账笔数</span>
        <span class="stat-value">{{ count }}<small> 笔</small></span>
      </div>
      <div class="stat-tile">
        <span class="stat-label">日均支出</span>
        <span class="stat-value">¥{{ formatMoney(avgPerDay) }}</span>
      </div>
    </section>

    <el-skeleton v-if="loading" :rows="8" animated class="card" />

    <template v-else>
      <div class="stats-grid">
        <section class="card">
          <div class="card-head">
            <h2>一级分类占比</h2>
            <span class="muted small">共 {{ byL1.length }} 类</span>
          </div>

          <div v-if="!byL1.length" class="empty-box">
            <p class="empty-title">还没有数据</p>
            <p class="empty-sub">记几笔之后，这里会显示每类花销的占比。</p>
          </div>

          <template v-else>
            <div class="stack-bar">
              <i
                v-for="(item, index) in byL1"
                :key="item.id"
                :style="{ width: `${item.percent}%`, background: colorAt(index) }"
                :title="`${item.name} ${item.percent}%`"
              ></i>
            </div>
            <ul class="legend-list">
              <li v-for="(item, index) in byL1" :key="item.id" class="legend-item">
                <span class="legend-dot" :style="{ background: colorAt(index) }"></span>
                <span class="legend-name">{{ item.name }}</span>
                <span class="legend-pct">{{ item.percent.toFixed(1) }}%</span>
                <span class="legend-value">¥{{ formatMoney(item.total_cents) }}</span>
              </li>
            </ul>
          </template>
        </section>

        <section class="card">
          <div class="card-head">
            <h2>近 6 个月趋势</h2>
            <span class="muted small">合计 ¥{{ formatMoney(trendTotal) }}</span>
          </div>

          <div class="trend-chart">
            <div v-for="point in trend" :key="point.month" class="trend-col">
              <span class="trend-value">¥{{ (point.total_cents / 100).toFixed(0) }}</span>
              <div class="trend-track">
                <div
                  class="trend-bar"
                  :class="{ 'is-current': point.month === store.month }"
                  :style="{ height: `${Math.max((point.total_cents / trendMax) * 100, 2)}%` }"
                ></div>
              </div>
              <span class="trend-label" :class="{ 'is-current': point.month === store.month }">
                {{ trendLabel(point.month) }}
              </span>
            </div>
          </div>
        </section>
      </div>

      <section class="card">
        <div class="card-head">
          <h2>二级分类排行</h2>
          <span class="muted small">前 10 名</span>
        </div>

        <div v-if="!byL2.length" class="empty-box">
          <p class="empty-title">还没有数据</p>
          <p class="empty-sub">记几笔之后，这里会显示花钱最多的二级分类。</p>
        </div>

        <ul v-else class="rank-list rank-list-lg">
          <li v-for="(item, index) in byL2.slice(0, 10)" :key="item.id" class="rank-item">
            <span class="rank-index">{{ index + 1 }}</span>
            <span class="rank-name">{{ item.name }}</span>
            <span class="rank-bar">
              <i :style="{ width: `${Math.max((item.total_cents / byL2[0].total_cents) * 100, 3)}%` }"></i>
            </span>
            <span class="rank-value">¥{{ formatMoney(item.total_cents) }}</span>
            <span class="rank-pct">{{ item.percent.toFixed(0) }}%</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
