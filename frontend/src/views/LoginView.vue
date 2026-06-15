<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const isRegister = ref(false)

const form = reactive({
  username: '',
  password: '',
  full_name: ''
})

function toggleMode() {
  isRegister.value = !isRegister.value
  errorMessage.value = ''
  successMessage.value = ''
}

async function submit() {
  loading.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    if (isRegister.value) {
      await http.post('/auth/register', form)
      successMessage.value = '注册成功，正在登录...'
      // 注册成功后自动登录
      await authStore.login({ username: form.username, password: form.password })
      router.push('/')
    } else {
      await authStore.login(form)
      router.push('/')
    }
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel">
      <div>
        <p class="eyebrow">Text Style Transfer</p>
        <h1>{{ isRegister ? '注册账号' : '文本迁移演示系统' }}</h1>
        <p class="muted">
          {{ isRegister ? '创建新账号以使用风格迁移功能。' : '支持选择模型、角色与保存历史记录。' }}
        </p>
      </div>

      <form class="form-grid" @submit.prevent="submit">
        <label v-if="isRegister">
          <span>姓名</span>
          <input v-model="form.full_name" placeholder="请输入姓名" required />
        </label>

        <label>
          <span>用户名</span>
          <input v-model="form.username" placeholder="请输入用户名" required />
        </label>

        <label>
          <span>密码</span>
          <input v-model="form.password" type="password" placeholder="请输入密码" required />
        </label>

        <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
        <p v-if="successMessage" class="success-text">{{ successMessage }}</p>

        <button class="primary-button" :disabled="loading">
          {{ loading ? '请稍候...' : isRegister ? '注册' : '登录系统' }}
        </button>
      </form>

      <p class="toggle-mode">
        {{ isRegister ? '已有账号？' : '没有账号？' }}
        <a href="#" @click.prevent="toggleMode">
          {{ isRegister ? '去登录' : '去注册' }}
        </a>
      </p>
    </section>
  </main>
</template>
