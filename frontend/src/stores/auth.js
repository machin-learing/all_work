import { defineStore } from 'pinia'

import http from '../api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    profile: null
  }),
  actions: {
    async login(form) {
      const { data } = await http.post('/auth/login', form)
      this.token = data.access_token
      localStorage.setItem('token', data.access_token)
      await this.fetchProfile()
    },
    async fetchProfile() {
      if (!this.token) return
      const { data } = await http.get('/users/me')
      this.profile = data
    },
    logout() {
      this.token = ''
      this.profile = null
      localStorage.removeItem('token')
    }
  }
})
