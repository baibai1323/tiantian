import { createRouter, createWebHashHistory } from 'vue-router'

import HomeView from './views/HomeView.vue'
import BillsView from './views/BillsView.vue'
import StatsView from './views/StatsView.vue'
import SettingsView from './views/SettingsView.vue'
import CategoryView from './views/CategoryView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView, meta: { title: '首页' } },
    { path: '/bills', name: 'bills', component: BillsView, meta: { title: '账单' } },
    { path: '/stats', name: 'stats', component: StatsView, meta: { title: '统计' } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '设置' } },
    { path: '/settings/categories', name: 'categories', component: CategoryView, meta: { title: '分类管理' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
