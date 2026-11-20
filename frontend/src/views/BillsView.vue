<script setup>
// 账单页：按天分组展示当前月份的支出，支持分类筛选、关键词搜索、
// 分页加载（每次 100 条）、导出 CSV、编辑和删除。
// 删除是「软删除」：记录先移入回收站，之后还能恢复，不是立刻从数据库消失。
// 月份来自全局 store，切到别的月份时本页会重新加载。
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Search, Delete, EditPen, Plus } from '@element-plus/icons-vue'

import { api } from '../api'
import { store, formatMoney, formatDate } from '../state'

// route 读取地址栏参数，router 用于跳转。进入页面时如果地址带 category_l1，
// 就说明是从首页分类排行点进来的，需要默认按该分类过滤。
const route = useRoute()
const router = useRouter()

// items 是已经加载到前端的账单；total 是后端符合条件的总条数；
// sumCents 是这些账单的金额合计（单位：分，1 元 = 100 分）。
const items = ref([])
const total = ref(0)
const sumCents = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const categoryL1 = ref(route.query.category_l1 ? Number(route.query.category_l1) : '')
const keyword = ref('')

// 每页条数。账单可能很多，一次性全查会慢，所以分批加载，点「加载更多」再取下一页。
// keywordTimer 用来做搜索防抖：停止输入 300 毫秒后才真正发请求，避免每敲一个字都查一次。
const PAGE_SIZE = 100
let keywordTimer = null

// 把账单按日期分组，供模板按天渲染。
// Map 保存「日期 -> 当天账单列表」，再转成数组并按日期倒序（新的在前），
// 每组顺便算出当天合计。合计用分做整数加法，避免小数浮点误差。
const groups = computed(() => {
  // 用 Map 按日期建桶：同一天第一次出现时先建空数组，再把账单追加进去。
  const map = new Map()
  for (const item of items.value) {
    if (!map.has(item.spent_on)) map.set(item.spent_on, [])
    map.get(item.spent_on).push(item)
  }
  // 日期字符串 "YYYY-MM-DD" 可以直接按字典序比较，大的就是更晚的日期。
  // reduce 把当天的金额累加起来，初始值为 0；分是整数，不会有小数误差。
  return Array.from(map.entries())
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, list]) => ({
      date,
      list,
      total: list.reduce((acc, x) => acc + x.amount_cents, 0),
    }))
})

// 已加载条数小于总数，说明后面还有，显示「加载更多」按钮。
const hasMore = computed(() => items.value.length < total.value)

/**
 * 加载账单列表。
 * reset 为 true 时是重新查询（切换筛选、删除后刷新），从第 0 条开始并清空旧数据；
 * 为 false 时是「加载更多」，偏移量接在已加载条数后面，把新数据追加到列表尾部。
 * 请求参数里的 q 是搜索词，会同时匹配备注和二级分类名。
 */
async function load(reset = true) {
  // 重置时打开整页骨架屏；加载更多时只让按钮转圈，页面已有内容保持不动。
  if (reset) loading.value = true
  else loadingMore.value = true
  try {
    // 查询参数集中在这里：月份、一级分类、关键词和分页偏移量。
    const data = await api.expenses({
      month: store.month,
      category_l1: categoryL1.value || '',
      q: keyword.value.trim(),
      limit: PAGE_SIZE,
      // offset 用已加载条数，保证第二页从第一页结束的位置继续。
      offset: reset ? 0 : items.value.length,
    })
    // reset 时直接替换列表，否则把新一页拼到旧列表后面。
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

// 导出当前月份为 CSV。直接打开后端生成的下载地址，由浏览器处理文件保存。
// CSV 是一种用逗号分隔的纯文本表格格式，Excel、Numbers 都能打开。
function exportCsv() {
  window.open(api.exportUrl(store.month), '_blank')
}

/**
 * 删除一笔账单，实际动作是「移入回收站」。
 * 先弹确认框，用户点「再想想」或关闭弹窗就取消；确认后才调用删除接口。
 * 删除成功后广播数据变化并刷新列表，保证合计和条数同步更新。
 */
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
    // 删除成功后刷新当前列表；store.changed() 让其他页面也重新取数。
    ElMessage.success('已移入回收站')
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '删除失败')
  }
}

// 一级分类一改就立刻重新查询，不需要用户再点按钮。
watch(categoryL1, () => load())
// 关键词搜索做防抖：每次输入先清掉上一次的定时器，300 毫秒内没有新输入才发请求。
// 这样连续打字只会产生最后一次查询，减少无谓的网络请求。
watch(keyword, () => {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => load(), 300)
})

// 页面第一次显示时加载第一页账单。
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
