<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, ArrowRight } from '@element-plus/icons-vue'

import { api } from '../api'
import { store, formatMoney, formatDate, monthLabel, currentMonth } from '../state'

const router = useRouter()
const loading = ref(true)
const summary = ref(null)
const error = ref('')

const total = computed(() => (summary.value ? summary.value.total_cents : 0))
const today = computed(() => (summary.value ? summary.value.today_cents : 0))
const count = computed(() => (summary.value ? summary.value.count : 0))
const recent = computed(() => (summary.value ? summary.value.recent : []))
const byL1 = computed(() => (summary.value ? summary.value.by_l1 : []))

const maxL1 = computed(() => Math.max(...byL1.value.map((x) => x.total_cents), 1))

const isThisMonth = computed(() => store.month === currentMonth())

function daysInMonth(month) {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m, 0).getDate()
}

const avgPerDay = computed(() => {
  // 当月按已过天数算，历史月份按整月天数算
  const days = isThisMonth.value ? new Date().getDate() : daysInMonth(store.month)
  return Math.round(total.value / Math.max(days, 1))
})

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

function goBills(categoryL1) {
  router.push({ path: '/bills', query: categoryL1 ? { category_l1: categoryL1 } : {} })
}

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
