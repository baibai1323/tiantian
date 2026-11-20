<script setup>
// 回收站页：集中处理「已经删除但还能恢复」的账单。
// 账单页的删除是软删除（只做标记、不真正移除数据），记录会先来到这里；
// 在这里可以恢复，也可以彻底删除（真正从数据库删除，之后无法找回）。
// 回收站是一个缓冲区：删除后先放这里，避免手滑造成不可逆的损失。
// 本页的恢复、彻底删除、清空都会立即影响列表的合计与条数。
// 彻底删除的记录不会进入任何「最近删除」列表，是真的从数据库移除。
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, RefreshLeft } from '@element-plus/icons-vue'

import { api } from '../api'
import { store, formatMoney, formatDate } from '../state'

// items 是当前已加载的回收站记录，total 是总数，sumCents 是金额合计（单位：分）。
// loading 控制首次加载的骨架屏，loadingMore 控制「加载更多」按钮的转圈。
const items = ref([])
const total = ref(0)
const sumCents = ref(0)
const loading = ref(true)
const loadingMore = ref(false)

// 每次取 100 条，记录多时点「加载更多」继续取，避免一次渲染太多行卡顿。
const PAGE_SIZE = 100

// 已加载数量小于总数，说明还有下一页。
const hasMore = computed(() => items.value.length < total.value)

/**
 * 加载回收站列表。
 * reset 为 true 表示重新加载（首次进入、恢复或删除后刷新），从第 0 条开始并替换列表；
 * 为 false 表示加载更多，偏移量接在已加载条数后面，把结果追加到末尾。
 * 回收站接口只返回已删除的记录，并按删除时间倒序排列。
 */
async function load(reset = true) {
  if (reset) loading.value = true
  else loadingMore.value = true
  // 重新加载时替换整个列表，避免恢复或彻底删除后还留着已经处理过的记录。
  try {
    const data = await api.trash({
      limit: PAGE_SIZE,
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

/**
 * 恢复一笔账单：把它从回收站移回正常账单列表。
 * 恢复后调用 store.changed() 广播数据变化，首页和账单页会重新加载；
 * 当前页也刷新一次，让这条记录立刻从回收站消失。
 * 如果原分类已经被删除，后端会把它归入「其他 / 未分类」兜底。
 */
async function restore(item) {
  try {
    await api.restoreExpense(item.id)
    // 恢复成功后同步刷新全局状态，让首页和账单页也看到这笔记录。
    ElMessage.success('已恢复，回到账单里了')
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '恢复失败')
  }
}

/**
 * 彻底删除一笔账单，无法恢复。
 * 这是不可逆操作，所以先弹确认框，并把分类和金额写进提示，让用户确认删对了。
 * 用户取消时 ElMessageBox 会抛异常，直接 return，不调用接口。
 * 彻底删除后，导出 CSV 里也不会再包含这笔记录。
 */
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
    // 彻底删除后同样广播数据变化，并刷新当前回收站列表。
    ElMessage.success('已彻底删除')
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '彻底删除失败')
  }
}

/**
 * 清空回收站：把里面的记录全部彻底删除。
 * 没有记录时直接返回，避免弹出没有意义的确认框。
 * 确认文案里带上总条数，让用户清楚这次会删掉多少东西。
 * 清空和逐条彻底删除的效果一样，只是一次处理完。
 */
async function emptyTrash() {
  // 没有记录直接返回；按钮虽然已禁用，这里再兜一层，防止程序化调用。
  if (!total.value) return
  // 清空是不可逆操作，必须先让用户确认。
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
    // deleted 是后端返回的实际删除条数，用它给用户一个准确的结果。
    ElMessage.success(`已清空 ${res.deleted} 笔`)
    // 清空成功后刷新列表，页面会切回「回收站是空的」状态。
    store.changed()
    load()
  } catch (err) {
    ElMessage.error(err.message || '清空失败')
  }
}

// 页面首次显示时加载第一页回收站记录。
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
