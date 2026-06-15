<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const models = ref([])
const roles = ref([])
const records = ref([])
const loading = ref(false)
const showUserMenu = ref(false)

const form = reactive({
  source_text: '',
  role_code: '',
  model_code: ''
})

const chatMessages = ref([])
const chatContainer = ref(null)

const isAdmin = computed(() => authStore.profile?.is_admin)

async function loadMeta() {
  const [roleRes, modelRes] = await Promise.all([
    http.get('/meta/roles'),
    http.get('/meta/models')
  ])
  roles.value = roleRes.data
  models.value = modelRes.data
  if (!form.role_code && roles.value.length) form.role_code = roles.value[0].code
  if (!form.model_code && models.value.length) form.model_code = models.value[0].code
}

async function loadRecords() {
  const { data } = await http.get('/transfers')
  records.value = data
}

function roleLabel(code) {
  const r = roles.value.find(r => r.code === code)
  return r ? r.name : code
}

function modelLabel(code) {
  const m = models.value.find(m => m.code === code)
  return m ? m.name : code
}

function selectHistory(record) {
  form.role_code = record.role_code
  form.model_code = record.model_code
  chatMessages.value = [
    { type: 'user', text: record.source_text },
    { type: 'model', text: record.rewritten_text, role_code: record.role_code, model_code: record.model_code }
  ]
}

function newChat() {
  chatMessages.value = []
  form.source_text = ''
}

async function submitRewrite() {
  const text = form.source_text.trim()
  if (!text || loading.value) return
  loading.value = true
  chatMessages.value.push({ type: 'user', text })

  try {
    const { data } = await http.post('/transfers', {
      source_text: text,
      role_code: form.role_code,
      model_code: form.model_code
    })
    chatMessages.value.push({
      type: 'model',
      text: data.rewritten_text,
      role_code: data.role_code,
      model_code: data.model_code
    })
    records.value.unshift(data)
  } catch (error) {
    chatMessages.value.push({
      type: 'model',
      text: '[错误] ' + (error.response?.data?.detail || '请求失败'),
      role_code: form.role_code,
      model_code: form.model_code,
      isError: true
    })
  } finally {
    form.source_text = ''
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

function logout() {
  authStore.logout()
  router.push('/login')
}

onMounted(async () => {
  if (!authStore.profile) await authStore.fetchProfile()
  await Promise.all([loadMeta(), loadRecords()])
})
</script>

<template>
  <div class="app-layout">
    <!-- ====== 左侧边栏 ====== -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2>风格迁移</h2>
        <button class="new-chat-btn" @click="newChat">+ 新对话</button>
      </div>

      <!-- 历史记录 -->
      <div class="history-list">
        <div
          v-for="record in records"
          :key="record.id"
          class="history-item"
          @click="selectHistory(record)"
        >
          <div class="history-role">{{ roleLabel(record.role_code) }}</div>
          <div class="history-text">{{ record.source_text.slice(0, 40) }}{{ record.source_text.length > 40 ? '...' : '' }}</div>
          <div class="history-meta">{{ record.model_name }}</div>
        </div>
        <div v-if="records.length === 0" class="history-empty">暂无历史记录</div>
      </div>

      <!-- 底部用户区 -->
      <div class="sidebar-footer">
        <div class="user-bar" @click="showUserMenu = !showUserMenu">
          <div class="user-avatar">{{ authStore.profile?.full_name?.[0] || 'U' }}</div>
          <div class="user-info">
            <div class="user-name">{{ authStore.profile?.full_name }}</div>
            <div class="user-role-tag">{{ isAdmin ? '管理员' : '用户' }}</div>
          </div>
        </div>
        <div v-if="showUserMenu" class="user-menu">
          <div class="user-menu-item" @click="logout">退出登录</div>
        </div>
      </div>
    </aside>

    <!-- ====== 右侧主区域 ====== -->
    <main class="main-area">
      <!-- 角色选择栏 -->
      <div class="chat-header">
        <div class="role-selector">
          <span class="selector-label">说话对象</span>
          <select v-model="form.role_code">
            <option v-for="role in roles" :key="role.code" :value="role.code">
              {{ role.name }}
            </option>
          </select>
        </div>
        <div class="model-selector">
          <span class="selector-label">模型</span>
          <select v-model="form.model_code">
            <option v-for="model in models" :key="model.code" :value="model.code">
              {{ model.name }}
            </option>
          </select>
        </div>
      </div>

      <!-- 对话区域 -->
      <div class="chat-area" ref="chatContainer">
        <div v-if="chatMessages.length === 0" class="chat-placeholder">
          <div class="placeholder-icon">💬</div>
          <h3>选择一个说话对象，开始对话</h3>
          <p>输入你想说的话，模型会根据你选择的角色改写语气和措辞</p>
        </div>

        <div v-for="(msg, idx) in chatMessages" :key="idx" class="message-row"
             :class="msg.type === 'user' ? 'message-right' : 'message-left'">
          <div v-if="msg.type === 'model'" class="avatar model-avatar">
            {{ roleLabel(msg.role_code)?.[0] || 'M' }}
          </div>
          <div class="bubble" :class="{
            'bubble-user': msg.type === 'user',
            'bubble-model': msg.type === 'model',
            'bubble-error': msg.isError
          }">
            <div v-if="msg.type === 'model'" class="bubble-meta">
              {{ roleLabel(msg.role_code) }} · {{ modelLabel(msg.model_code) }}
            </div>
            <div class="bubble-text">{{ msg.text }}</div>
          </div>
          <div v-if="msg.type === 'user'" class="avatar user-avatar">
            {{ authStore.profile?.full_name?.[0] || 'U' }}
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-bar">
        <textarea
          v-model="form.source_text"
          placeholder="输入你想说的话，例如：我今天加班，可能晚点回去。"
          rows="1"
          @keydown.enter.exact.prevent="submitRewrite"
          :disabled="loading"
        />
        <button
          class="send-btn"
          :disabled="!form.source_text.trim() || loading"
          @click="submitRewrite"
        >
          发送
        </button>
      </div>
    </main>
  </div>
</template>
