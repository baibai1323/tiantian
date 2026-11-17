<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Search, Delete, EditPen, Plus } from '@element-plus/icons-vue'

import { api } from '../api'
import { store, formatMoney, formatDate } from '../state'

const route = useRoute()
const router = useRouter()

const items = ref([])
const total = ref(0)
const sumCents = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const categoryL1 = ref(route.query.category_l1 ? Number(route.query.category_l1) : '')
const keyword = ref('')

const PAGE_SIZE = 100
let keywordTimer = null

const groups = computed(() => {
  const map = new Map()
  for (const item of items.value) {
    if (!map.has(item.spent_on)) map.set(item.spent_on, [])
    map.get(item.spent_on).push(item)
  }
  return Array.from(map.entries())
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, list]) => ({
      date,
      list,
      total: list.reduce((acc, x) => acc + x.amount_cents, 0),
    }))
})

const hasMore = computed(() => items.value.length < total.value)

async function load(reset = true) {
  if (reset) loading.value = true
  else loadingMore.value = true
  try {
    const data = await api.expenses({
      month: store.month,
      category_l1: categoryL1.value || '',
      q: keyword.value.trim(),
      limit: PAGE_SIZE,
      offset: reset ? 0 : items.value.length,
    })
    items.value = reset ? data.items : [...items.value, ...data.items]
    total.value = data.total
    sumCents.value = data.sum_cents
  } catch (err) {
    ElMessage.error(err.message || '加载失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function exportCsv() {
  window.open(api.exportUrl(store.month), '_blank')
}

async function remove(item) {
  try {
    await ElMessageBox.confirm(
      `删除「${item.category_l2_name} ¥${formatMoney(item.amount_cents)}」这笔记录？删除后会移入「回收站」，不是永久删除；要恢复或彻底删除，请到回收站里操作。`,
      '移入回收站',
      { confirmButtonText: '移入回收站', cancelButtonText: '再想想', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.deleteExpense(item.id)
    ElMessage.success('已移入回收站')
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '删除失败')
  }
}

watch(categoryL1, () => load())
watch(keyword, () => {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => load(), 300)
})

onMounted(load)
</script>

<template>
  <div class="bills">
    <section class="card filter-card">
      <div class="filter-row">
        <el-select v-model="categoryL1" placeholder="全部一级分类" clearable class="filter-select">
          <el-option v-for="c in store.categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="搜备注、二级分类…"
          :prefix-icon="Search"
          clearable
          class="filter-search"
        />
        <div class="filter-actions">
          <el-button :icon="Delete" text @click="router.push('/trash')">回收站</el-button>
          <el-button :icon="Download" @click="exportCsv">导出 CSV</el-button>
          <el-button type="primary" :icon="Plus" @click="store.openDialog()">记一笔</el-button>
        </div>
      </div>
      <div class="filter-summary">
        共 <strong>{{ total }}</strong> 笔，合计 <strong class="money">¥{{ formatMoney(sumCents) }}</strong>
      </div>
    </section>

    <el-skeleton v-if="loading" :rows="6" animated class="card" />

    <div v-else-if="!groups.length" class="card empty-box">
      <p class="empty-title">这个月还没有账单</p>
      <p class="empty-sub">换个分类或月份看看，或者现在记一笔。</p>
    </div>

    <template v-else>
      <section v-for="group in groups" :key="group.date" class="card day-card">
        <div class="day-head">
          <div>
            <strong>{{ formatDate(group.date) }}</strong>
            <span class="muted small">{{ group.date }}</span>
          </div>
          <span class="muted">合计 ¥{{ formatMoney(group.total) }}</span>
        </div>

        <ul class="bill-list">
          <li
            v-for="item in group.list"
            :key="item.id"
            class="bill-item"
          >
            <div class="bill-icon">{{ item.category_l2_name.slice(0, 1) }}</div>
            <div class="bill-body">
              <div class="bill-title">
                <span>{{ item.category_l1_name }} / {{ item.category_l2_name }}</span>
              </div>
              <div class="bill-note">{{ item.note || '无备注' }}</div>
            </div>
            <div class="bill-amount">¥{{ formatMoney(item.amount_cents) }}</div>
            <div class="bill-actions">
              <el-button size="small" text :icon="EditPen" @click="store.openDialog(item)">编辑</el-button>
              <el-button size="small" text type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
            </div>
          </li>
        </ul>
      </section>

      <div v-if="hasMore" class="load-more">
        <el-button :loading="loadingMore" @click="load(false)">
          加载更多（还有 {{ total - items.length }} 笔）
        </el-button>
      </div>
    </template>
  </div>
</template>
