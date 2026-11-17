<script setup>
import { computed, onMounted, ref } from 'vue'

import { api } from '../api'
import { store, formatMoney, monthLabel } from '../state'

const loading = ref(true)
const summary = ref(null)
const trend = ref([])
const error = ref('')

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

const total = computed(() => (summary.value ? summary.value.total_cents : 0))
const count = computed(() => (summary.value ? summary.value.count : 0))
const byL1 = computed(() => (summary.value ? summary.value.by_l1 : []))
const byL2 = computed(() => (summary.value ? summary.value.by_l2 : []))

const avgPerDay = computed(() => {
  const now = new Date()
  const isThisMonth = store.month === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const days = isThisMonth ? now.getDate() : new Date(Number(store.month.slice(0, 4)), Number(store.month.slice(5, 7)), 0).getDate()
  return Math.round(total.value / Math.max(days, 1))
})

const trendMax = computed(() => Math.max(...trend.value.map((x) => x.total_cents), 1))
const trendTotal = computed(() => trend.value.reduce((acc, x) => acc + x.total_cents, 0))

function colorAt(index) {
  return palette[index % palette.length]
}

function trendLabel(month) {
  return `${Number(month.slice(5, 7))} 月`
}

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
