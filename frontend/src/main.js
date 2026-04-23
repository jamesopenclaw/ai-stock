import { createApp } from 'vue'
import 'element-plus/theme-chalk/dark/css-vars.css'
// 编程式 API 不会经过按需组件扫描，需显式引入样式，否则确认框会缺少布局（如叠在视口左上角）
import 'element-plus/es/components/message-box/style/css'
import { ElLoadingDirective } from 'element-plus'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.directive('loading', ElLoadingDirective)
app.use(router)
app.mount('#app')
