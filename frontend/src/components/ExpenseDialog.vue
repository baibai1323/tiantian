<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { api } from '../api'
import { store, formatMoney } from '../state'

const saving = ref(false)
const formRef = ref(null)

const form = reactive({
  amount: '',
  categories: [],
  spent_on: today(),
  note: '',
})

function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const cascaderProps = {
  value: 'id',
  label: 'name',
  children: 'children',
  expandTrigger: 'click',
}

const categoryOptions = computed(() =>
  store.categories.map((l1) => ({
    id: l1.id,
    name: l1.name,
    children: (l1.children || []).map((l2) => ({ id: l2.id, name: l2.name })),
  })),
)

const quickAmounts = [10, 20, 30, 50, 100]

const isEditing = computed(() => Boolean(store.editing))

watch(
  () => store.dialogVisible,
  (visible) => {
    if (!visible) return
    if (store.editing) {
      form.amount = (store.editing.amount_cents / 100).toFixed(2)
      form.categories = [store.editing.category_l1, store.editing.category_l2]
      form.spent_on = store.editing.spent_on
      form.note = store.editing.note || ''
    } else {
      form.amount = ''
      form.categories = []
      form.spent_on = today()
      form.note = ''
    }
  },
)

function sanitizeAmount(value) {
  let v = String(value).replace(/[^\d.]/g, '')
  const firstDot = v.indexOf('.')
  if (firstDot !== -1) {
    v = v.slice(0, firstDot + 1) + v.slice(firstDot + 1).replace(/\./g, '')
    v = v.slice(0, firstDot + 3)
  }
  return v
}

function onAmountInput(e) {
  form.amount = sanitizeAmount(e.target.value)
}

function setAmount(value) {
  form.amount = String(value)
}

function validate() {
  const amount = Number(form.amount)
  if (!form.amount || Number.isNaN(amount) || amount <= 0) {
    ElMessage.warning('请填写大于 0 的金额')
    return false
  }
  if (form.categories.length !== 2) {
    ElMessage.warning('请选择分类')
    return false
  }
  if (!form.spent_on) {
    ElMessage.warning('请选择日期')
    return false
  }
  return true
}

async function save(continueAfter = false) {
  if (saving.value || !validate()) return
  saving.value = true
  const payload = {
    amount: Number(form.amount),
    category_l2: form.categories[1],
    spent_on: form.spent_on,
    note: form.note.trim(),
  }
  try {
    if (isEditing.value) {
      await api.updateExpense(store.editing.id, payload)
      ElMessage.success('已修改')
    } else {
      await api.createExpense(payload)
      ElMessage.success(`已记下 ¥${formatMoney(Number(form.amount) * 100)}`)
    }
    store.changed()
    if (continueAfter) {
      store.editing = null
      form.amount = ''
      form.note = ''
      form.spent_on = today()
    } else {
      store.closeDialog()
    }
  } catch (err) {
    ElMessage.error(err.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const dateShortcuts = [
  { text: '今天', value: () => new Date() },
  {
    text: '昨天',
    value: () => {
      const d = new Date()
      d.setDate(d.getDate() - 1)
      return d
    },
  },
]
</script>

<template>
  <el-dialog
    :model-value="store.dialogVisible"
    :title="isEditing ? '修改这笔' : '记一笔'"
    width="520px"
    align-center
    class="expense-dialog"
    :close-on-click-modal="false"
    @update:model-value="(v) => !v && store.closeDialog()"
  >
    <div class="amount-box">
      <span class="currency">¥</span>
      <input
        :value="form.amount"
        class="amount-input"
        inputmode="decimal"
        placeholder="0.00"
        autofocus
        @input="onAmountInput"
        @keyup.enter="save(false)"
      />
    </div>

    <div class="quick-row">
      <button v-for="q in quickAmounts" :key="q" type="button" class="quick-chip" @click="setAmount(q)">
        {{ q }}
      </button>
      <span class="quick-hint">元</span>
    </div>

    <el-form label-position="top" @submit.prevent>
      <el-form-item label="分类">
        <el-cascader
          v-model="form.categories"
          :options="categoryOptions"
          :props="cascaderProps"
          placeholder="选一级分类，再选二级分类"
          class="w-full"
          separator=" / "
          clearable
        />
      </el-form-item>

      <div class="form-row">
        <el-form-item label="日期" class="grow">
          <el-date-picker
            v-model="form.spent_on"
            type="date"
            format="YYYY 年 MM 月 DD 日"
            value-format="YYYY-MM-DD"
            :clearable="false"
            :shortcuts="dateShortcuts"
            class="w-full"
          />
        </el-form-item>
      </div>

      <el-form-item label="备注（可不填）">
        <el-input
          v-model="form.note"
          maxlength="100"
          show-word-limit
          placeholder="比如：和同事吃午饭"
          @keyup.enter="save(false)"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="store.closeDialog()">取消</el-button>
        <el-button v-if="!isEditing" :loading="saving" @click="save(true)">保存，再记一笔</el-button>
        <el-button type="primary" :loading="saving" @click="save(false)">
          {{ isEditing ? '保存修改' : '保存' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>
