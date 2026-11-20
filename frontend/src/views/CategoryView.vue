<script setup>
// 分类管理页：维护两级分类体系。
// 一级分类是大类（吃饭、交通…），二级分类是小类（午饭、地铁…）。
// 两级分类的意义：记账时先选大类再选小类，既方便输入，也方便按层级统计。
// 系统自带的分类只能查看，用户自建的可以改名、删除；
// 删除分类不会丢账单，账单会迁移到「其他 / 未分类」这个兜底分类。
// 分类名限制 16 个字，弹窗输入框的 maxlength 会同步提示剩余字数。
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Delete, Edit, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { api } from '../api'
import { store } from '../state'

// router 用于返回设置页。
const router = useRouter()
// roots 是后端返回的分类树（一级带 children），loading 控制整页 loading 遮罩。
const roots = ref([])
const loading = ref(true)

// 下面五个变量共同控制「新增/改名」小弹窗：
// dialogMode 区分三种模式（新增一级、新增二级、改名），
// dialogName 是输入框内容，dialogParent 是新建小类时挂到哪个一级分类下，
// dialogTarget 是改名时要改的那条分类，saving 防止重复提交。
const dialogVisible = ref(false)
const dialogMode = ref('add-root')
const dialogName = ref('')
const dialogParent = ref(null)
const dialogTarget = ref(null)
const saving = ref(false)

// 弹窗标题随模式变化，单独用 ref 保存，模板直接绑定。
const dialogTitle = ref('新增一级分类')

/**
 * 加载分类树，供页面列表渲染。
 * 用 manageCategories 而不是普通分类接口，是因为管理页还需要
 * 每个分类下的账单数量（expense_count）和是否为系统分类（is_system）。
 */
async function load() {
  loading.value = true
  try {
    roots.value = await api.manageCategories()
  } catch (error) {
    ElMessage.error(error.message || '加载分类失败')
  } finally {
    loading.value = false
  }
}

// 打开「新增一级分类」弹窗：清空名称、父子关联和目标，避免带上一次的状态。
// 三种模式共用一个弹窗，切换模式时要把不相关的字段清空。
function openAddRoot() {
  dialogMode.value = 'add-root'
  dialogTitle.value = '新增一级分类'
  dialogName.value = ''
  dialogParent.value = null
  dialogTarget.value = null
  dialogVisible.value = true
}

// 打开「新增二级分类」弹窗，并记住父分类，保存时要把 parent_id 一起提交。
// dialogTarget 置空，表示这次不是改名。
function openAddChild(parent) {
  dialogMode.value = 'add-child'
  dialogTitle.value = `在「${parent.name}」下新增小类`
  dialogName.value = ''
  dialogParent.value = parent
  dialogTarget.value = null
  dialogVisible.value = true
}

// 打开改名弹窗：把原名字填进输入框，并记住要修改的分类对象。
// dialogParent 置空，改名不涉及父分类。
function openRename(item) {
  dialogMode.value = 'edit'
  dialogTitle.value = '修改分类名称'
  dialogName.value = item.name
  dialogParent.value = null
  dialogTarget.value = item
  dialogVisible.value = true
}

/**
 * 保存分类：根据当前模式决定是改名还是新增。
 * 名字先 trim 掉首尾空格，空名字直接提示，不往后端发请求。
 * 改名时只提交 name；新增二级分类时额外带上 parent_id。
 * 保存成功后同时刷新本地分类树和全局分类缓存，保证其他页面的下拉框也更新。
 */
async function save() {
  // 去掉首尾空格，避免用户只输入空格也能创建分类。
  const name = dialogName.value.trim()
  if (!name) {
    ElMessage.warning('请输入分类名')
    return
  }
  saving.value = true
  try {
    // 编辑模式且确实有目标对象时才走更新，否则按新增处理。
    if (dialogMode.value === 'edit' && dialogTarget.value) {
      // 改名只影响分类本身，历史账单的金额和日期都不会变，显示名会自动跟着新名字走。
      await api.updateCategory(dialogTarget.value.id, { name })
      ElMessage.success('已改名，历史账单会显示新名字')
    } else {
      const body = { name }
      // 只有新增二级分类才需要 parent_id；新增一级分类不传，后端会当作根节点。
      if (dialogMode.value === 'add-child' && dialogParent.value) body.parent_id = dialogParent.value.id
      await api.createCategory(body)
      ElMessage.success('已新增分类')
    }
    dialogVisible.value = false
    // 两个刷新互不依赖，用 Promise.all 并行执行，少等一轮。
    await Promise.all([load(), store.loadCategories(true)])
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 删除分类。
 * 先判断是不是一级分类：一级分类被删时，它下面的小类也会一起删。
 * 再根据 expense_count 生成不同的提示，明确告诉用户账单会被迁移而不是丢失。
 * 用户取消确认框时直接返回，不调用删除接口。
 */
async function remove(item) {
  // 只有自建的一级分类才会出现在 roots 里且 is_system 为 false。
  const isRoot = !item.is_system && roots.value.some((r) => r.id === item.id)
  // 根据分类下有没有账单，生成不同提示，让用户知道删除的后果。
  const tip = item.expense_count
    ? `「${item.name}」下还有 ${item.expense_count} 笔账单，删除后会全部归入「其他 / 未分类」。`
    : `「${item.name}」下没有账单，可以直接删除。`
  try {
    await ElMessageBox.confirm(
      `${tip}${isRoot ? '它下面的小类也会一起删除。' : ''}删除后不能恢复。`,
      '删除分类',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    // 用户取消确认框时 ElMessageBox 会抛异常，这里静默结束即可。
    return
  }
  try {
    // 接口会返回被迁移的账单数量，用于给用户更准确的反馈。
    // 确认后调用删除接口；后端会把该分类下的账单迁移到兜底分类。
    const result = await api.deleteCategory(item.id)
    ElMessage.success(result.migrated ? `已删除，${result.migrated} 笔账单已归入「其他 / 未分类」` : '已删除')
    await Promise.all([load(), store.loadCategories(true)])
  } catch (error) {
    ElMessage.error(error.message || '删除失败')
  }
}

// 页面首次显示时加载分类树，之后由弹窗里的保存、删除操作触发局部刷新。
onMounted(load)
</script>

<template>
  <div class="category-page">
    <div class="cat-head">
      <el-button :icon="ArrowLeft" text @click="router.push('/settings')">返回设置</el-button>
      <div class="cat-head-text">
        <p class="muted">
          系统自带的 10 个大类只能查看；你自己新增的分类可以改名、删除。删除时账单会迁移到「其他 / 未分类」。
        </p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openAddRoot">新增一级分类</el-button>
    </div>

    <div v-loading="loading" class="cat-list">
      <section v-for="root in roots" :key="root.id" class="cat-group">
        <header class="cat-group-head">
          <div class="cat-title">
            <span class="cat-icon">{{ root.icon || root.name.slice(0, 1) }}</span>
            <strong>{{ root.name }}</strong>
            <el-tag v-if="root.is_system" size="small" type="info" effect="plain">系统</el-tag>
            <span class="muted small">{{ root.expense_count }} 笔</span>
          </div>
          <div class="cat-actions">
            <el-button size="small" text :icon="Plus" @click="openAddChild(root)">加小类</el-button>
            <template v-if="!root.is_system">
              <el-button size="small" text :icon="Edit" @click="openRename(root)">改名</el-button>
              <el-button size="small" text type="danger" :icon="Delete" @click="remove(root)">删除</el-button>
            </template>
          </div>
        </header>

        <div class="cat-children">
          <div v-for="child in root.children" :key="child.id" class="cat-child">
            <span class="cat-child-name">{{ child.name }}</span>
            <el-tag v-if="child.is_system" size="small" type="info" effect="plain">系统</el-tag>
            <span class="muted small cat-child-count">{{ child.expense_count }} 笔</span>
            <div v-if="!child.is_system" class="cat-actions">
              <el-button size="small" text :icon="Edit" @click="openRename(child)">改名</el-button>
              <el-button size="small" text type="danger" :icon="Delete" @click="remove(child)">删除</el-button>
            </div>
          </div>
          <p v-if="!root.children.length" class="muted small cat-empty">还没有小类，点「加小类」建一个。</p>
        </div>
      </section>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="420px" destroy-on-close>
      <el-input
        v-model="dialogName"
        maxlength="16"
        show-word-limit
        placeholder="例如：宠物、猫粮、夜宵"
        @keyup.enter="save"
      />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
