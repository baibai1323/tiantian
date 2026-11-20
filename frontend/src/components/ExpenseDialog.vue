<script setup>
// 本文件是「记一笔」弹窗组件：新增支出和修改支出共用这一个界面。
// 组件（component）：Vue 中可复用的界面单元，逻辑、模板、样式可以写在一起。
// 弹窗是否显示由全局 store 统一控制，页面上的「记一笔」按钮只负责打开它。
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { api } from '../api'
import { store, formatMoney } from '../state'

// saving：保存请求是否正在进行中。
// 它用来禁用按钮、显示 loading，防止用户连点两次重复记一笔。
// ref 是 Vue 的响应式容器：把值包起来，值一变界面就自动更新。
const saving = ref(false)
// formRef 预留给表单校验；当前版本用 validate() 手动校验，还没有绑到模板上。
const formRef = ref(null)

// 表单数据集中放在一个 reactive 对象里。
// reactive 让对象的每个字段都变成响应式的，输入框改动会同步回这里。
// 金额故意用字符串而不是数字：输入过程中会出现 "12." 这种中间状态，
// 用字符串才能原样保留用户正在敲的内容，提交前再转成数字。
const form = reactive({
  amount: '',
  categories: [],
  spent_on: today(),
  note: '',
})

/**
 * 返回今天的日期，格式固定为 YYYY-MM-DD。
 * 后端和数据库都按这个格式存日期，前端不能直接用 Date 对象传过去。
 * padStart(2, '0') 用来补零：9 月要显示成 09，保证字符串长度一致。
 */
function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// Element Plus 级联选择器的字段映射：告诉它用 id 做值、name 做显示文字、
// children 找下一级，点一下就直接展开下一级（expandTrigger: 'click'）。
const cascaderProps = {
  value: 'id',
  label: 'name',
  children: 'children',
  expandTrigger: 'click',
}

// 把全局分类树改造成级联选择器需要的结构，只保留 id、name、children 三个字段。
// 两级分类联动：选了第一级，选择器才会展开第二级；账单最终只记第二级。
// computed 是计算属性：依赖的分类数据变了，它会自动重新计算，不需要手动更新。
const categoryOptions = computed(() =>
  store.categories.map((l1) => ({
    id: l1.id,
    name: l1.name,
    children: (l1.children || []).map((l2) => ({ id: l2.id, name: l2.name })),
  })),
)

// 快捷金额：把最常用的几档金额做成按钮，点一下直接填入，少敲几次键盘。
// 这些数字只是输入辅助，不做限制，用户仍可手动输入任意金额。
const quickAmounts = [10, 20, 30, 50, 100]

// 有 store.editing 就说明是在改旧账单，否则是新增。
// Boolean() 把对象或 null 统一转成 true / false，模板里好判断。
const isEditing = computed(() => Boolean(store.editing))

// 监听弹窗打开的动作，每次打开都重置表单。
// 编辑时把旧账单的金额、分类、日期、备注回填；新增时清空成默认值。
// 这样同一个弹窗可以反复使用，不会残留上一次的输入。
// watch 是侦听器：指定的数据变化时执行回调，这里监听弹窗可见性。
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

/**
 * 清洗金额输入，只保留合法的数字和小数点。
 * 规则：先去掉所有非数字、非小数点字符；只允许出现一个小数点；
 * 小数部分最多两位（金额最小单位是分）。这样从源头避免用户输入
 * "1.2.3"、"-5"、"12 元" 这类后端无法解析的内容。
 */
function sanitizeAmount(value) {
  let v = String(value).replace(/[^\d.]/g, '')
  // 找到第一个小数点的位置；没有小数点就只保留整数部分。
  const firstDot = v.indexOf('.')
  if (firstDot !== -1) {
    // 去掉后面的小数点，再把小数位截到两位（下标 +3 正好包含两位小数）。
    v = v.slice(0, firstDot + 1) + v.slice(firstDot + 1).replace(/\./g, '')
    v = v.slice(0, firstDot + 3)
  }
  return v
}

// 输入框每次键入都会触发；先清洗再写回表单，界面显示的就是清洗后的值。
function onAmountInput(e) {
  form.amount = sanitizeAmount(e.target.value)
}

// 快捷金额按钮的点击处理：直接把数字转成字符串填进表单。
function setAmount(value) {
  form.amount = String(value)
}

/**
 * 提交前的前端校验，三项都通过才允许保存。
 * 金额必须能转成大于 0 的数字；分类必须正好选满两级；
 * 日期不能为空。校验失败时用消息提示告诉用户缺什么，并返回 false。
 */
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

/**
 * 保存这笔支出。
 * continueAfter 为 true 时表示「保存，再记一笔」：保存成功后不关弹窗，
 * 只清空金额和备注并保留日期，方便连续录入多笔。
 * 编辑模式调用更新接口，新增模式调用创建接口；两者提交的字段相同。
 * 成功后调用 store.changed() 通知其他页面数据已变，需要重新加载。
 */
async function save(continueAfter = false) {
  if (saving.value || !validate()) return
  saving.value = true
  // 只提交后端需要的字段；分类提交第二级（小类）的 id，
  // 一级分类由后端根据小类的父子关系推导，避免前后端各存一份造成不一致。
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
    // 保存成功后统一广播「数据变了」，首页、账单页、统计页会各自刷新。
    store.changed()
    // 连续记账时保留日期，只清金额和备注，下一笔通常还是同一天。
    if (continueAfter) {
      store.editing = null
      form.amount = ''
      form.note = ''
      form.spent_on = today()
    } else {
      store.closeDialog()
    }
  } catch (err) {
    // 后端返回的错误优先展示，取不到再用兜底文案。
    ElMessage.error(err.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// 日期选择器的快捷选项：今天、昨天。
// 用函数返回 Date，是因为每次点开弹窗都要基于「当前时间」重新算，
// 不能把日期在模块加载时就算死。
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
