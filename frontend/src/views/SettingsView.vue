<script setup>
import { computed, onMounted, ref } from 'vue'
import { Download, FolderOpened, Lock, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { api } from '../api'
import { store } from '../state'

const health = ref(null)
const loading = ref(true)
const importing = ref(false)
const resultVisible = ref(false)
const result = ref(null)

const categories = computed(() => store.categories)
const totalL2 = computed(() =>
  categories.value.reduce((acc, item) => acc + (item.children ? item.children.length : 0), 0),
)

function exportCsv() {
  window.open(api.exportUrl(store.month), '_blank')
}

async function handleFile(uploadFile) {
  const raw = uploadFile && uploadFile.raw
  if (!raw) return
  importing.value = true
  try {
    const text = await raw.text()
    result.value = await api.importCsv(text)
    resultVisible.value = true
  } catch (error) {
    ElMessage.error(error.message || '导入失败')
  } finally {
    importing.value = false
  }
}

function onResultClosed() {
  // 关闭结果框后再刷新页面数据，避免弹窗被路由重建顶掉
  store.changed()
}

onMounted(async () => {
  try {
    health.value = await api.health()
    await store.loadCategories()
  } catch {
    // 设置页不阻塞
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="settings">
    <section class="card">
      <div class="card-head">
        <h2>数据与备份</h2>
        <el-tag size="small" type="success">只存在本机</el-tag>
      </div>

      <div class="setting-row">
        <div class="setting-label">
          <el-icon><FolderOpened /></el-icon>
          <div>
            <strong>数据目录</strong>
            <p class="muted small">数据库文件 tiantian.db 和自动备份都在这里。</p>
          </div>
        </div>
        <code class="path-text">{{ health ? health.data_dir : '读取中…' }}</code>
      </div>

      <div class="setting-row">
        <div class="setting-label">
          <el-icon><Lock /></el-icon>
          <div>
            <strong>自动备份</strong>
            <p class="muted small">每次启动时备份一次数据库，最多保留 7 份。</p>
          </div>
        </div>
        <span class="muted small">backups/ 目录</span>
      </div>

      <div class="setting-row">
        <div class="setting-label">
          <el-icon><Download /></el-icon>
          <div>
            <strong>导出账单</strong>
            <p class="muted small">导出当前月份为 CSV，可用 Excel 或 Numbers 打开。</p>
          </div>
        </div>
        <el-button :icon="Download" @click="exportCsv">导出 {{ store.month }}</el-button>
      </div>

      <div class="setting-row">
        <div class="setting-label">
          <el-icon><Upload /></el-icon>
          <div>
            <strong>导入账单</strong>
            <p class="muted small">
              选择天天记账导出的 CSV；重复记录自动跳过，分类不存在时归入「其他 / 未分类」。
            </p>
          </div>
        </div>
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".csv,text/csv"
          :on-change="handleFile"
        >
          <el-button :icon="Upload" :loading="importing">选择 CSV 导入</el-button>
        </el-upload>
      </div>
    </section>

    <el-dialog v-model="resultVisible" title="导入结果" width="520px" @closed="onResultClosed">
      <template v-if="result">
        <div class="import-stats">
          <div><strong>{{ result.imported }}</strong><span>成功导入</span></div>
          <div><strong>{{ result.duplicates }}</strong><span>跳过重复</span></div>
          <div><strong>{{ result.invalid }}</strong><span>无效行</span></div>
          <div><strong>{{ result.fallback }}</strong><span>归入其他</span></div>
        </div>

        <div v-if="result.errors.length" class="import-issues">
          <p class="muted small">这些行没有导入：</p>
          <ul>
            <li v-for="item in result.errors" :key="'e' + item.line">
              第 {{ item.line }} 行：{{ item.reason }}
            </li>
          </ul>
        </div>

        <div v-if="result.warnings.length" class="import-issues">
          <p class="muted small">这些行的分类被兜底：</p>
          <ul>
            <li v-for="item in result.warnings" :key="'w' + item.line">
              第 {{ item.line }} 行：{{ item.reason }}
            </li>
          </ul>
        </div>

        <p v-if="!result.imported && !result.duplicates && !result.invalid" class="muted small">
          文件里没有可导入的账单。
        </p>
      </template>
      <template #footer>
        <el-button type="primary" @click="resultVisible = false">知道了</el-button>
      </template>
    </el-dialog>

    <section class="card">
      <div class="card-head">
        <h2>分类体系</h2>
        <span class="muted small">{{ categories.length }} 个一级 · {{ totalL2 }} 个二级</span>
      </div>
      <div class="category-grid">
        <div v-for="item in categories" :key="item.id" class="category-chip">
          <strong>{{ item.name }}</strong>
          <span class="muted small">{{ item.children ? item.children.length : 0 }} 个小类</span>
        </div>
      </div>
    </section>

    <section class="card about-card">
      <div class="card-head">
        <h2>关于天天记账</h2>
        <span class="muted small">v{{ health ? health.version : store.version }}</span>
      </div>
      <p class="about-text">
        天天记账是一款只做支出的桌面记账工具：人民币、两级分类、数据完全留在本机。
        界面按宽屏设计，同时适配小窗口和手机尺寸，方便以后扩展。
      </p>
      <p class="about-text muted small">
        技术栈：FastAPI + SQLModel + SQLite，前端 Vue 3 + Element Plus，桌面外壳 PyWebView。
      </p>
    </section>
  </div>
</template>
