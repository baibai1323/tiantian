// 路由表：把浏览器地址里的路径映射到对应的页面组件。
// 从 vue-router 引入两个函数：createRouter 创建路由器，createWebHashHistory 使用哈希模式。
import { createRouter, createWebHashHistory } from 'vue-router'

// 页面组件：每个 .vue 文件对应一个路由页面。
import HomeView from './views/HomeView.vue'
import BillsView from './views/BillsView.vue'
import StatsView from './views/StatsView.vue'
import SettingsView from './views/SettingsView.vue'
import CategoryView from './views/CategoryView.vue'
import TrashView from './views/TrashView.vue'

// 导出路由实例，main.js 会用 app.use(router) 把它安装到应用上。
export const router = createRouter({
  // 哈希模式：地址形如 /#/bills，井号后面的部分不会发给服务器。
  // 桌面程序用 file:// 或本地端口打开时，刷新和深链接都不用后端配置回退路由，
  // 打包成 exe 后最稳妥，所以这里特意不用 history 模式。
  history: createWebHashHistory(),
  routes: [
    // meta.title 会被 App.vue 读取，用来显示顶部的页面标题。
    { path: '/', name: 'home', component: HomeView, meta: { title: '首页' } },
    { path: '/bills', name: 'bills', component: BillsView, meta: { title: '账单' } },
    { path: '/trash', name: 'trash', component: TrashView, meta: { title: '回收站' } },
    { path: '/stats', name: 'stats', component: StatsView, meta: { title: '统计' } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '设置' } },
    { path: '/settings/categories', name: 'categories', component: CategoryView, meta: { title: '分类管理' } },
    // 兜底路由：地址写错或过期链接都跳回首页，避免出现空白页。
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  // 每次切换页面都滚回顶部，否则从长列表点进详情会停在中间位置。
  scrollBehavior: () => ({ top: 0 }),
})
