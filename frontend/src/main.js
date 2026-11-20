// 应用入口：把 Vue、Element Plus、路由挂到 index.html 的 #app 节点上。
// 这里做的都是“全局只执行一次”的初始化，所以没有对外导出任何东西。
// Vue 3 的 createApp 用来创建应用实例。
import { createApp } from 'vue'
// Element Plus 是 UI 组件库；zhCn 是它的中文语言包（日期选择器等内置文案用）。
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
// 图标库整体导入，下面会一次性注册成全局组件。
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
// 组件库自带的样式必须引入，否则按钮、表格没有外观。
import 'element-plus/dist/index.css'

// 根组件、路由表、全局样式。
import App from './App.vue'
import { router } from './router'
import './styles.css'

// 创建应用实例，App.vue 是整棵组件树的根。
const app = createApp(App)

// 遍历图标库的每个导出（如 Plus、Delete），逐个注册成全局组件；
// 这样任何模板里都能直接写 <Plus />，不用每个文件单独 import。
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  // key 是图标名，component 是对应的组件定义。
  app.component(key, component)
}

// use() 用来安装插件：Element Plus 负责界面组件，router 负责页面切换。
// locale 指定中文，让组件内建的文字（如“清空”“确定”）显示中文。
app.use(ElementPlus, { locale: zhCn })
app.use(router)
// 挂载到 index.html 中 id="app" 的容器，应用从这一行开始真正渲染。
app.mount('#app')
