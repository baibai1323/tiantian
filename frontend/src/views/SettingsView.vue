<script setup>
// 设置页：展示数据目录、备份说明，提供 CSV 导出/导入和分类管理入口。
// 「只存在本机」是产品承诺：数据库和备份都放在用户电脑上，不上传云端。
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Download, FolderOpened, Lock, Setting, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { api } from '../api'
import { store } from '../state'

// router 用于跳转到分类管理页。
const router = useRouter()

// health 存后端返回的运行信息（数据目录、版本号等）；
// importing 控制导入按钮的 loading；resultVisible / result 控制导入结果弹窗和内容。
const health = ref(null)
const loading = ref(true)
const importing = ref(false)
const resultVisible = ref(false)
const result = ref(null)

// 分类数据来自全局 store，进入页面时会加载一次。
// totalL2 统计所有一级分类下的小类总数，用于展示「多少个二级」。
const categories = computed(() => store.categories)
const totalL2 = computed(() =>
  categories.value.reduce((acc, item) => acc + (item.children ? item.children.length : 0), 0),
)

/**
 * 导出当前月份账单。
 * 直接打开后端生成的 CSV 下载地址，交给浏览器保存文件；
 * 前端不拼文件内容，因为字段顺序和编码（带 BOM 才能让 Excel 正确识别中文）由后端统一保证。
 */
function exportCsv() {
  window.open(api.exportUrl(store.month), '_blank')
}

/**
 * 处理用户选择的 CSV 文件。
 * el-upload 设置了 auto-upload=false，所以文件不会自动上传，
 * 这里手动读取文本内容，再交给后端解析导入。
 * uploadFile.raw 是浏览器原生的 File 对象，调用 text() 得到 UTF-8 文本。
 */
async function handleFile(uploadFile) {
  const raw = uploadFile && uploadFile.raw
  // 没有拿到文件对象就直接返回，避免后面的 raw.text() 报错。
  if (!raw) return
  importing.value = true
  // 导入成功后先显示结果弹窗，等用户关闭后再刷新页面数据（见 onResultClosed）。
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

// 关闭导入结果弹窗后的回调。
// 不在导入成功时立刻刷新：刷新会重建页面组件，可能把刚打开的结果弹窗顶掉，
// 用户就看不到「成功多少、跳过多少」的统计了。所以等弹窗关闭后再广播数据变化。
function onResultClosed() {
  // 关闭结果框后再刷新页面数据，避免弹窗被路由重建顶掉
  store.changed()
}

/**
 * 页面加载时读取后端健康信息和分类列表。
 * 设置页即使接口失败也不阻塞：错误被吞掉，页面仍显示静态说明和「读取中…」。
 */
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

      <div class="setting-row">
        <div class="setting-label">
          <el-icon><Setting /></el-icon>
          <div>
            <strong>分类管理</strong>
            <p class="muted small">
              新增、改名或删除自己创建的分类；系统自带的 10 个大类不能改。
            </p>
          </div>
        </div>
        <el-button :icon="Setting" @click="router.push('/settings/categories')">管理分类</el-button>
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
