const app = getApp()

Page({
  data: {
    user: null,
    today: '',
    debug: false
  },

  onShow() {
    // 未登录 → 回登录页
    if (!(app.globalData.user || wx.getStorageSync('user'))) {
      app.ensureLogin().then((u) => {
        if (!u) {
          wx.reLaunch({ url: '/pages/login/login' })
          return
        }
        this.applyUser(u)
      })
      return
    }
    this.applyUser(app.globalData.user || wx.getStorageSync('user'))
  },

  applyUser(u) {
    this.setData({
      user: u,
      today: this.fmtDate(new Date()),
      debug: (u && u.debug_mode) || false
    })
  },

  fmtDate(d) {
    const p = (n) => (n < 10 ? '0' + n : '' + n)
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
  },

  goTrip() { wx.navigateTo({ url: '/pages/trip/trip' }) },
  goRefuel() { wx.navigateTo({ url: '/pages/refuel/refuel' }) },
  goMaintain() { wx.navigateTo({ url: '/pages/maintain/maintain' }) },
  goReports() { wx.navigateTo({ url: '/pages/reports/reports' }) },

  goAdmin() {
    if (!this.data.user || !this.data.user.is_admin) {
      wx.showToast({ title: '仅管理员可进入', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/admin/admin' })
  },

  // 退出登录：回到登录页重新选择账号
  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定退出当前账号吗？',
      confirmColor: '#e64340',
      success: (res) => {
        if (res.confirm) {
          app.logout()
          wx.reLaunch({ url: '/pages/login/login' })
        }
      }
    })
  },

  // 调试模式切换用户
  onSwitchUser() {
    wx.showModal({
      title: '切换调试用户',
      editable: true,
      placeholderText: '输入 userid，如 dev001',
      success: (res) => {
        if (res.confirm && res.content) {
          app.switchUser(res.content.trim()).then((u) => {
            this.setData({ user: u, debug: u && u.debug_mode })
            wx.showToast({ title: '已切换为 ' + (u ? u.name : ''), icon: 'none' })
          })
        }
      }
    })
  }
})
