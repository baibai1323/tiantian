<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, RefreshLeft } from '@element-plus/icons-vue'

import { api } from '../api'
import { store, formatMoney, formatDate } from '../state'

const items = ref([])
const total = ref(0)
const sumCents = ref(0)
const loading = ref(true)
const loadingMore = ref(false)

const PAGE_SIZE = 100

const hasMore = computed(() => items.value.length < total.value)

async function load(reset = true) {
  if (reset) loading.value = true
  else loadingMore.value = true
  try {
    const data = await api.trash({
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

async function restore(item) {
  try {
    await api.restoreExpense(item.id)
    ElMessage.success('已恢复，回到账单里了')
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '恢复失败')
  }
}

async function purge(item) {
  try {
    await ElMessageBox.confirm(
      `彻底删除「${item.category_l1_name} / ${item.category_l2_name} ¥${formatMoney(item.amount_cents)}」？\n\n彻底删除后无法恢复，也不会再出现在导出文件里。`,
      '彻底删除',
      {
        confirmButtonText: '彻底删除',
        cancelButtonText: '取消',
        type: 'error',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    await api.purgeExpense(item.id)
    ElMessage.success('已彻底删除')
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '彻底删除失败')
  }
}

async function emptyTrash() {
  if (!total.value) return
  try {
    await ElMessageBox.confirm(
      `回收站里有 ${total.value} 笔记录，清空后全部彻底删除，无法恢复。`,
      '清空回收站',
      {
        confirmButtonText: '全部彻底删除',
        cancelButtonText: '取消',
        type: 'error',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    const res = await api.emptyTrash()
    ElMessage.success(`已清空 ${res.deleted} 笔`)
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '清空失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="trash-page">
    <section class="card trash-head">
      <p class="trash-sub">
        删除的账单会先放在这里，可以恢复；确认不要了，再彻底删除。彻底删除后无法找回。
      </p>
      <el-button
        type="danger"
        plain
        :icon="Delete"
        :disabled="!total"
        @click="emptyTrash"
      >
        清空回收站
      </el-button>
    </section>

    <el-skeleton v-if="loading" :rows="5" animated class="card" />

    <div v-else-if="!items.length" class="card empty-box trash-empty">
      <p class="empty-title">回收站是空的</p>
      <p class="empty-sub">在账单页删除的记录，会先来到这里。</p>
    </div>

    <template v-else>
      <section class="card trash-list-card">
        <div class="trash-summary">
          共 <strong>{{ total }}</strong> 笔，合计
          <strong class="money">¥{{ formatMoney(sumCents) }}</strong>
        </div>

        <ul class="bill-list">
          <li v-for="item in items" :key="item.id" class="bill-item">
            <div class="bill-icon">{{ item.category_l2_name.slice(0, 1) }}</div>
            <div class="bill-body">
              <div class="bill-title">
                <span>{{ item.category_l1_name }} / {{ item.category_l2_name }}</span>
                <span class="muted small">记于 {{ formatDate(item.spent_on) }}</span>
              </div>
              <div class="bill-note">{{ item.note || '无备注' }}</div>
            </div>
            <div class="bill-amount">¥{{ formatMoney(item.amount_cents) }}</div>
            <div class="bill-actions">
              <el-button size="small" text type="primary" :icon="RefreshLeft" @click="restore(item)">
                恢复
              </el-button>
              <el-button size="small" text type="danger" :icon="Delete" @click="purge(item)">
                彻底删除
              </el-button>
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
