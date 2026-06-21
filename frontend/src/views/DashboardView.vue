<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const models = ref([])
const roles = ref([])
const records = ref([])
const acceptedSamples = ref([])
const loading = ref(false)
const showUserMenu = ref(false)
const showAcceptedSamples = ref(false)
const chatMessages = ref([])
const chatContainer = ref(null)
const acceptedMap = reactive({})

const examples = [
  '我今天加班，可能晚点回去',
  '我明天要开会，晚点再回复你',
  '我刚到医院，检查结果还没出来',
  '我这周项目有点赶，可能没时间一起吃饭'
]

const form = reactive({
  source_text: '',
  role_code: '',
  model_code: '',
  mode: 'single'
})

const isAdmin = computed(() => authStore.profile?.is_admin)
const groupedAcceptedSamples = computed(() => {
  const roleOrder = new Map(roles.value.map((role, index) => [role.code, index]))
  const groups = new Map()
  acceptedSamples.value.forEach(sample => {
    const key = sample.role_code
    if (!groups.has(key)) {
      groups.set(key, {
        role_code: sample.role_code,
        role_name: sample.role_name,
        samples: []
      })
    }
    groups.get(key).samples.push(sample)
  })
  return Array.from(groups.values()).sort((left, right) => {
    return (roleOrder.get(left.role_code) ?? 99) - (roleOrder.get(right.role_code) ?? 99)
  })
})

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

async function loadAcceptedSamples() {
  const { data } = await http.get('/accepted-samples')
  acceptedSamples.value = data
  Object.keys(acceptedMap).forEach(key => {
    delete acceptedMap[key]
  })
  data.forEach(sample => {
    acceptedMap[sample.transfer_id] = sample
  })
}

function roleLabel(code) {
  return roles.value.find(role => role.code === code)?.name || code
}

function modelLabel(code) {
  return models.value.find(model => model.code === code)?.name || code
}

function selectHistory(record) {
  showAcceptedSamples.value = false
  form.role_code = record.role_code
  form.model_code = record.model_code
  form.mode = 'single'
  chatMessages.value = [
    { type: 'user', text: record.source_text },
    {
      type: 'model',
      text: record.rewritten_text,
      role_code: record.role_code,
      model_code: record.model_code,
      transfer_id: record.id
    }
  ]
}

function newChat() {
  showAcceptedSamples.value = false
  chatMessages.value = []
  form.source_text = ''
}

function useExample(example) {
  form.source_text = example
}

async function createTransfer(text, roleCode, modelCode) {
  const { data } = await http.post('/transfers', {
    source_text: text,
    role_code: roleCode,
    model_code: modelCode
  })
  return data
}

async function submitSingle(text) {
  const data = await createTransfer(text, form.role_code, form.model_code)
  chatMessages.value.push({
    type: 'model',
    text: data.rewritten_text,
    role_code: data.role_code,
    model_code: data.model_code,
    transfer_id: data.id
  })
  records.value.unshift(data)
}

async function submitRoleCompare(text) {
  const settled = await Promise.allSettled(
    roles.value.map(role => createTransfer(text, role.code, form.model_code))
  )
  const results = settled.map((result, index) => {
    const role = roles.value[index]
    if (result.status === 'fulfilled') {
      records.value.unshift(result.value)
      return {
        role_code: result.value.role_code,
        model_code: result.value.model_code,
        transfer_id: result.value.id,
        text: result.value.rewritten_text
      }
    }
    return {
      role_code: role.code,
      model_code: form.model_code,
      text: result.reason?.response?.data?.detail || '请求失败',
      isError: true
    }
  })
  chatMessages.value.push({
    type: 'comparison',
    title: `五角色对比 · ${modelLabel(form.model_code)}`,
    results
  })
}

async function submitModelCompare(text) {
  const settled = await Promise.allSettled(
    models.value.map(model => createTransfer(text, form.role_code, model.code))
  )
  const results = settled.map((result, index) => {
    const model = models.value[index]
    if (result.status === 'fulfilled') {
      records.value.unshift(result.value)
      return {
        role_code: result.value.role_code,
        model_code: result.value.model_code,
        transfer_id: result.value.id,
        text: result.value.rewritten_text
      }
    }
    return {
      role_code: form.role_code,
      model_code: model.code,
      text: result.reason?.response?.data?.detail || '请求失败',
      isError: true
    }
  })
  chatMessages.value.push({
    type: 'comparison',
    title: `多模型对比 · ${roleLabel(form.role_code)}`,
    results
  })
}

async function submitRewrite() {
  const text = form.source_text.trim()
  if (!text || loading.value) return

  showAcceptedSamples.value = false
  loading.value = true
  chatMessages.value.push({ type: 'user', text })

  try {
    if (form.mode === 'roles') {
      await submitRoleCompare(text)
    } else if (form.mode === 'models') {
      await submitModelCompare(text)
    } else {
      await submitSingle(text)
    }
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

function reviewStatusLabel(status) {
  const labels = {
    pending: '待审核',
    approved: '已采纳入库',
    rejected: '已拒绝'
  }
  return labels[status] || status
}

async function likeSample(item) {
  if (!item.transfer_id || acceptedMap[item.transfer_id]) return
  item.acceptError = ''
  try {
    const { data } = await http.post('/accepted-samples', {
      transfer_id: item.transfer_id
    })
    acceptedMap[item.transfer_id] = data
    acceptedSamples.value.unshift(data)
  } catch (error) {
    item.acceptError = error.response?.data?.detail || '点赞失败'
  }
}

async function unlikeSample(item) {
  if (!item.transfer_id || !acceptedMap[item.transfer_id]) return
  item.acceptError = ''
  try {
    await http.delete(`/accepted-samples/by-transfer/${item.transfer_id}`)
    delete acceptedMap[item.transfer_id]
    acceptedSamples.value = acceptedSamples.value.filter(sample => {
      return sample.transfer_id !== item.transfer_id
    })
  } catch (error) {
    item.acceptError = error.response?.data?.detail || '取消点赞失败'
  }
}

function toggleLike(item) {
  if (acceptedMap[item.transfer_id]) {
    return unlikeSample(item)
  }
  return likeSample(item)
}

async function openAcceptedSamples() {
  showAcceptedSamples.value = true
  await loadAcceptedSamples()
}

async function reviewSample(sample, reviewStatus) {
  sample.reviewError = ''
  try {
    const { data } = await http.patch(`/accepted-samples/${sample.id}/review`, {
      review_status: reviewStatus
    })
    Object.assign(sample, data)
  } catch (error) {
    sample.reviewError = error.response?.data?.detail || '审核失败'
  }
}

async function downloadApprovedSamples() {
  const { data } = await http.get('/accepted-samples/export', {
    responseType: 'blob'
  })
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = 'approved_samples.jsonl'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
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
  await loadAcceptedSamples()
})
</script>

<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2>风格迁移</h2>
        <button class="new-chat-btn" @click="newChat">+ 新对话</button>
      </div>

      <div class="history-list">
        <div
          v-for="record in records"
          :key="record.id"
          class="history-item"
          @click="selectHistory(record)"
        >
          <div class="history-role">{{ roleLabel(record.role_code) }}</div>
          <div class="history-text">
            {{ record.source_text.slice(0, 40) }}{{ record.source_text.length > 40 ? '...' : '' }}
          </div>
          <div class="history-meta">{{ modelLabel(record.model_code) }}</div>
        </div>
        <div v-if="records.length === 0" class="history-empty">暂无历史记录</div>
      </div>

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

    <main class="main-area">
      <div class="chat-header">
        <div class="mode-tabs">
          <button :class="{ active: form.mode === 'single' }" @click="form.mode = 'single'">
            单次改写
          </button>
          <button :class="{ active: form.mode === 'roles' }" @click="form.mode = 'roles'">
            五角色对比
          </button>
          <button :class="{ active: form.mode === 'models' }" @click="form.mode = 'models'">
            多模型对比
          </button>
        </div>

        <button
          v-if="isAdmin"
          class="sample-pool-btn"
          :class="{ active: showAcceptedSamples }"
          @click="openAcceptedSamples"
        >
          点赞样本池
        </button>

        <div class="role-selector" v-if="form.mode !== 'roles'">
          <span class="selector-label">对象</span>
          <select v-model="form.role_code">
            <option v-for="role in roles" :key="role.code" :value="role.code">
              {{ role.name }}
            </option>
          </select>
        </div>

        <div class="model-selector" v-if="form.mode !== 'models'">
          <span class="selector-label">模型</span>
          <select v-model="form.model_code">
            <option v-for="model in models" :key="model.code" :value="model.code">
              {{ modelLabel(model.code) }}
            </option>
          </select>
        </div>
      </div>

      <div class="example-row">
        <span>示例</span>
        <button v-for="example in examples" :key="example" @click="useExample(example)">
          {{ example }}
        </button>
      </div>

      <div class="chat-area" ref="chatContainer">
        <div v-if="showAcceptedSamples" class="sample-pool">
          <div class="sample-pool-header">
            <div>
              <h3>点赞样本池</h3>
              <p>用户点赞后进入待审核，管理员确认后再采纳为二次训练数据。</p>
            </div>
            <button class="download-samples-btn" @click="downloadApprovedSamples">
              下载已采纳数据
            </button>
          </div>
          <div v-if="acceptedSamples.length === 0" class="history-empty">暂无点赞样本</div>
          <div
            v-for="group in groupedAcceptedSamples"
            :key="group.role_code"
            class="sample-role-group"
          >
            <div class="sample-role-title">
              <span>{{ group.role_name }}</span>
              <small>{{ group.samples.length }} 条</small>
            </div>
            <div
              v-for="sample in group.samples"
              :key="sample.id"
              class="sample-item"
            >
              <div class="sample-meta">
                {{ modelLabel(sample.model_code) }} · {{ sample.username }} · {{ reviewStatusLabel(sample.review_status) }}
              </div>
              <div class="sample-source">{{ sample.source_text }}</div>
              <div class="sample-output">{{ sample.rewritten_text }}</div>
              <div class="sample-actions" v-if="isAdmin">
                <button
                  class="review-btn approve"
                  :disabled="sample.review_status === 'approved'"
                  @click="reviewSample(sample, 'approved')"
                >
                  采纳入库
                </button>
                <button
                  class="review-btn reject"
                  :disabled="sample.review_status === 'rejected'"
                  @click="reviewSample(sample, 'rejected')"
                >
                  拒绝
                </button>
                <button
                  class="review-btn"
                  :disabled="sample.review_status === 'pending'"
                  @click="reviewSample(sample, 'pending')"
                >
                  恢复待审
                </button>
              </div>
              <div v-if="sample.reviewError" class="accept-error">{{ sample.reviewError }}</div>
            </div>
          </div>
        </div>

        <div v-else-if="chatMessages.length === 0" class="chat-placeholder">
          <div class="placeholder-icon">文本风格迁移</div>
          <h3>输入一句话开始改写</h3>
        </div>

        <template v-if="!showAcceptedSamples">
          <div
            v-for="(msg, idx) in chatMessages"
            :key="idx"
            class="message-row"
            :class="msg.type === 'user' ? 'message-right' : 'message-left'"
          >
            <template v-if="msg.type === 'comparison'">
              <div class="comparison-panel">
                <div class="comparison-title">{{ msg.title }}</div>
                <div class="comparison-grid">
                  <div
                    v-for="(item, itemIdx) in msg.results"
                    :key="itemIdx"
                    class="comparison-card"
                    :class="{ 'comparison-error': item.isError }"
                  >
                    <div class="comparison-meta">
                      {{ roleLabel(item.role_code) }} · {{ modelLabel(item.model_code) }}
                    </div>
                    <div class="comparison-text">{{ item.text }}</div>
                    <button
                      v-if="!item.isError"
                      class="accept-btn"
                      @click="toggleLike(item)"
                    >
                      {{ acceptedMap[item.transfer_id] ? '取消点赞' : '点赞' }}
                    </button>
                    <div v-if="item.acceptError" class="accept-error">{{ item.acceptError }}</div>
                  </div>
                </div>
              </div>
            </template>

            <template v-else>
              <div v-if="msg.type === 'model'" class="avatar model-avatar">
                {{ roleLabel(msg.role_code)?.[0] || 'M' }}
              </div>
              <div
                class="bubble"
                :class="{
                  'bubble-user': msg.type === 'user',
                  'bubble-model': msg.type === 'model',
                  'bubble-error': msg.isError
                }"
              >
                <div v-if="msg.type === 'model'" class="bubble-meta">
                  {{ roleLabel(msg.role_code) }} · {{ modelLabel(msg.model_code) }}
                </div>
                <div class="bubble-text">{{ msg.text }}</div>
                <button
                  v-if="msg.type === 'model' && !msg.isError"
                  class="accept-btn"
                  @click="toggleLike(msg)"
                >
                  {{ acceptedMap[msg.transfer_id] ? '取消点赞' : '点赞' }}
                </button>
                <div v-if="msg.acceptError" class="accept-error">{{ msg.acceptError }}</div>
              </div>
              <div v-if="msg.type === 'user'" class="avatar user-avatar">
                {{ authStore.profile?.full_name?.[0] || 'U' }}
              </div>
            </template>
          </div>
        </template>
      </div>

      <div class="chat-input-bar">
        <textarea
          v-model="form.source_text"
          placeholder="输入你想改写的话，例如：我今天加班，可能晚点回去"
          rows="1"
          :disabled="loading"
          @keydown.enter.exact.prevent="submitRewrite"
        />
        <button
          class="send-btn"
          :disabled="!form.source_text.trim() || loading"
          @click="submitRewrite"
        >
          {{ loading ? '生成中' : '生成' }}
        </button>
      </div>
    </main>
  </div>
</template>
