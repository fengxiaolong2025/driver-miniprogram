// 登录页：首次打开提示登录；企业微信账号登录 / 调试账号登录
const app = getApp()
const api = require('../../utils/api')

Page({
  data: {
    wecomLoading: false,
    debugLoading: false,
    showDebug: false,      // 无企业微信环境（微信开发者工具）时显示调试登录
    debugUserid: '',
    err: ''
  },

  onLoad() {
    // 开发者工具 / 普通微信环境没有 wx.qy → 显示调试登录
    const hasWecom = !!(wx.qy && typeof wx.qy.login === 'function')
    this.setData({ showDebug: !hasWecom })

    // 已有本地 token：尝试自动恢复登录（服务重启后 token 失效则回落到登录界面）
    if (wx.getStorageSync('token')) {
      app.ensureLogin().then((u) => {
        if (u) wx.reLaunch({ url: '/pages/index/index' })
      })
    }
  },

  // 企业微信账号登录
  onWecomLogin() {
    if (this.data.wecomLoading) return
    if (!(wx.qy && typeof wx.qy.login === 'function')) {
      this.setData({ err: '当前不在企业微信环境，请使用调试账号登录' })
      return
    }
    this.setData({ wecomLoading: true, err: '' })
    wx.qy.login({
      success: (res) => {
        if (!res.code) {
          this.setData({ err: '未获取到登录凭证，请重试', wecomLoading: false })
          return
        }
        this.doLogin({ code: res.code }, 'wecom')
      },
      fail: () => {
        this.setData({ err: '企业微信登录失败，请重试', wecomLoading: false })
      }
    })
  },

  // 调试账号登录
  onDebugLogin() {
    const userid = this.data.debugUserid.trim()
    if (!userid) {
      this.setData({ err: '请输入调试账号 userid' })
      return
    }
    this.doLogin({ userid }, 'debug')
  },

  doLogin(payload, kind) {
    const loadingKey = kind === 'debug' ? 'debugLoading' : 'wecomLoading'
    this.setData({ [loadingKey]: true, err: '' })
    api.request('/api/login', 'POST', payload)
      .then((data) => {
        wx.setStorageSync('token', data.token)
        wx.setStorageSync('user', {
          userid: data.userid,
          name: data.name,
          is_admin: data.is_admin,
          debug_mode: data.debug_mode
        })
        app.globalData.user = {
          userid: data.userid,
          name: data.name,
          is_admin: data.is_admin,
          debug_mode: data.debug_mode
        }
        wx.reLaunch({ url: '/pages/index/index' })
      })
      .catch((e) => {
        this.setData({ err: e.error || '登录失败', [loadingKey]: false })
      })
  },

  onDebugInput(e) {
    this.setData({ debugUserid: e.detail.value, err: '' })
  }
})
