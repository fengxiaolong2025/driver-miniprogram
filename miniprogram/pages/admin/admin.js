const app = getApp()
const api = require('../../utils/api')

const TABS = ['车辆管理', '出发地管理', '目的地管理']

Page({
  data: {
    tabs: TABS,
    tab: 0,
    input: '',
    vehicles: [],
    origins: [],
    destinations: [],
    loading: false
  },

  onLoad() {
    this.load()
  },

  onTab(e) {
    this.setData({ tab: +e.currentTarget.dataset.index, input: '' })
  },

  onInput(e) { this.setData({ input: e.detail.value }) },

  load() {
    this.setData({ loading: true })
    api.request('/api/admin/vehicles', 'GET')
      .then((v) => this.setData({ vehicles: v.vehicles || [] }))
      .catch((err) => wx.showToast({ title: err.error || '加载失败', icon: 'none' }))
      .finally(() => this.setData({ loading: false }))
    api.request('/api/admin/locations', 'GET')
      .then((l) => this.setData({ origins: l.origins || [], destinations: l.destinations || [] }))
      .catch(() => {})
  },

  onAdd() {
    const { tab, input } = this.data
    const name = input.trim()
    if (!name) return wx.showToast({ title: '请输入内容', icon: 'none' })

    let req
    if (tab === 0) {
      req = api.request('/api/admin/vehicles', 'POST', { plate: name })
    } else {
      req = api.request('/api/admin/locations', 'POST', { name, kind: tab === 1 ? 'origin' : 'destination' })
    }
    req.then(() => {
      wx.showToast({ title: '已添加', icon: 'success' })
      this.setData({ input: '' })
      app.globalData.options = null // 失效缓存
      this.load()
    }).catch((err) => {
      wx.showToast({ title: err.error || '添加失败', icon: 'none' })
    })
  },

  onDelete(e) {
    const { tab } = this.data
    const name = e.currentTarget.dataset.name
    const kind = e.currentTarget.dataset.kind || ''
    wx.showModal({
      title: '确认删除',
      content: '删除「' + name + '」？',
      success: (res) => {
        if (!res.confirm) return
        let req
        if (tab === 0) {
          req = api.request('/api/admin/vehicles', 'DELETE', { plate: name })
        } else {
          req = api.request('/api/admin/locations', 'DELETE', { name, kind })
        }
        req.then(() => {
          wx.showToast({ title: '已删除', icon: 'none' })
          app.globalData.options = null
          this.load()
        }).catch((err) => {
          wx.showToast({ title: err.error || '删除失败', icon: 'none' })
        })
      }
    })
  }
})
