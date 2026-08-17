// 金成峰司机助手 · 小程序入口
const api = require('./utils/api')

App({
  globalData: {
    user: null,       // { userid, name, is_admin, debug_mode }
    options: null     // { vehicles, origins, destinations }
  },

  onLaunch() {
    // 登录改由登录页主导：首次打开进入登录页，登录成功后跳首页
  },

  // 校验本地 token 是否仍有效（服务重启后内存会话失效会落到 401）
  // 返回 Promise<user|null>：有效返回用户信息，无效返回 null（已清本地缓存）
  ensureLogin() {
    const token = wx.getStorageSync('token')
    if (!token) {
      this.globalData.user = null
      return Promise.resolve(null)
    }
    return api.request('/api/me', 'GET')
      .then((data) => {
        const user = {
          userid: data.userid,
          name: data.name,
          is_admin: data.is_admin,
          debug_mode: data.debug_mode
        }
        this.globalData.user = user
        wx.setStorageSync('user', user)
        return user
      })
      .catch((err) => {
        // 401 时 api.js 已清 token/user
        this.globalData.user = null
        if (err && err.needLogin) return null
        // 网络异常：保留本地缓存，容忍离线查看
        const cached = wx.getStorageSync('user')
        if (cached) {
          this.globalData.user = cached
          return cached
        }
        return null
      })
  },

  // 登录：POST /api/login（code=企业微信凭证 或 userid=调试账号），成功后写入本地缓存
  login(payload) {
    return api.request('/api/login', 'POST', payload).then((data) => {
      const user = {
        userid: data.userid,
        name: data.name,
        is_admin: data.is_admin,
        debug_mode: data.debug_mode
      }
      wx.setStorageSync('token', data.token)
      wx.setStorageSync('user', user)
      this.globalData.user = user
      return user
    })
  },

  // 退出登录：清空本地会话，回到登录页重新选择账号
  logout() {
    wx.removeStorageSync('token')
    wx.removeStorageSync('user')
    this.globalData.user = null
  },

  // 切换调试用户（仅调试场景使用）
  switchUser(userid) {
    this.logout()
    return this.login({ userid })
  },

  // 获取基础选项（车辆/地点），带缓存
  loadOptions(force) {
    if (this.globalData.options && !force) {
      return Promise.resolve(this.globalData.options)
    }
    return api.request('/api/options', 'GET')
      .then((data) => {
        this.globalData.options = data
        return data
      })
  }
})
