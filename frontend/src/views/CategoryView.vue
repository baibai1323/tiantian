<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Delete, Edit, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { api } from '../api'
import { store } from '../state'

const router = useRouter()
const roots = ref([])
const loading = ref(true)

const dialogVisible = ref(false)
const dialogMode = ref('add-root')
const dialogName = ref('')
const dialogParent = ref(null)
const dialogTarget = ref(null)
const saving = ref(false)

const dialogTitle = ref('新增一级分类')

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

function openAddRoot() {
  dialogMode.value = 'add-root'
  dialogTitle.value = '新增一级分类'
  dialogName.value = ''
  dialogParent.value = null
  dialogTarget.value = null
  dialogVisible.value = true
}

function openAddChild(parent) {
  dialogMode.value = 'add-child'
  dialogTitle.value = `在「${parent.name}」下新增小类`
  dialogName.value = ''
  dialogParent.value = parent
  dialogTarget.value = null
  dialogVisible.value = true
}

function openRename(item) {
  dialogMode.value = 'edit'
  dialogTitle.value = '修改分类名称'
  dialogName.value = item.name
  dialogParent.value = null
  dialogTarget.value = item
  dialogVisible.value = true
}

async function save() {
  const name = dialogName.value.trim()
  if (!name) {
    ElMessage.warning('请输入分类名')
    return
  }
  saving.value = true
  try {
    if (dialogMode.value === 'edit' && dialogTarget.value) {
      await api.updateCategory(dialogTarget.value.id, { name })
      ElMessage.success('已改名，历史账单会显示新名字')
    } else {
      const body = { name }
      if (dialogMode.value === 'add-child' && dialogParent.value) body.parent_id = dialogParent.value.id
      await api.createCategory(body)
      ElMessage.success('已新增分类')
    }
    dialogVisible.value = false
    await Promise.all([load(), store.loadCategories(true)])
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  const isRoot = !item.is_system && roots.value.some((r) => r.id === item.id)
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
    return
  }
  try {
    const result = await api.deleteCategory(item.id)
    ElMessage.success(result.migrated ? `已删除，${result.migrated} 笔账单已归入「其他 / 未分类」` : '已删除')
    await Promise.all([load(), store.loadCategories(true)])
  } catch (error) {
    ElMessage.error(error.message || '删除失败')
  }
}

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
