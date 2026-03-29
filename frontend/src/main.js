import { createApp } from 'vue'
import 'element-plus/theme-chalk/dark/css-vars.css'
import { ElLoadingDirective } from 'element-plus'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.directive('loading', ElLoadingDirective)
app.use(router)
app.mount('#app')
