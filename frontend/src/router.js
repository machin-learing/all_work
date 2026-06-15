import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from './stores/auth'
import DashboardView from './views/DashboardView.vue'
import LoginView from './views/LoginView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', name: 'dashboard', component: DashboardView, meta: { requiresAuth: true } }
  ]
})

router.beforeEach((to) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.token) {
    return '/login'
  }
  if (to.path === '/login' && authStore.token) {
    return '/'
  }
  return true
})

export default router
