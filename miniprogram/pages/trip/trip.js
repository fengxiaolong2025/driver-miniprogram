const app = getApp()
const api = require('../../utils/api')

Page({
  data: {
    vehicles: [],
    origins: [],
    destinations: [],
    vehIndex: -1,
    orgIndex: -1,
    dstIndex: -1,
    tripDate: '',
    today: '',
    submitting: false
  },

  onLoad() {
    this.setData({ tripDate: this.fmtDate(new Date()), today: this.fmtDate(new Date()) })
    this.loadOptions()
  },

  fmtDate(d) {
    const p = (n) => (n < 10 ? '0' + n : '' + n)
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
  },

  loadOptions() {
    app.loadOptions()
      .then((opt) => {
        const vehicles = (opt.vehicles || []).map((v) => v.plate)
        const origins = (opt.origins || []).map((v) => v.name)
        const destinations = (opt.destinations || []).map((v) => v.name)
        this.setData({ vehicles, origins, destinations })
        if (vehicles.length === 0) {
          wx.showToast({ title: '暂无车辆，请联系管理员添加', icon: 'none' })
        }
      })
      .catch((err) => {
        wx.showToast({ title: err.error || '加载失败', icon: 'none' })
      })
  },

  onVeh(e) { this.setData({ vehIndex: +e.detail.value }) },
  onOrg(e) { this.setData({ orgIndex: +e.detail.value }) },
  onDst(e) { this.setData({ dstIndex: +e.detail.value }) },
  onDate(e) { this.setData({ tripDate: e.detail.value }) },

  onSubmit() {
    const { vehicles, origins, destinations, vehIndex, orgIndex, dstIndex, tripDate } = this.data
    if (vehIndex < 0) return wx.showToast({ title: '请选择车牌号', icon: 'none' })
    if (orgIndex < 0) return wx.showToast({ title: '请选择出发地', icon: 'none' })
    if (dstIndex < 0) return wx.showToast({ title: '请选择目的地', icon: 'none' })
    if (origins[orgIndex] === destinations[dstIndex]) {
      return wx.showToast({ title: '出发地与目的地不能相同', icon: 'none' })
    }
    this.setData({ submitting: true })
    api.request('/api/trips', 'POST', {
      plate: vehicles[vehIndex],
      origin: origins[orgIndex],
      destination: destinations[dstIndex],
      trip_date: tripDate
    }).then(() => {
      wx.showToast({ title: '出车记录已提交', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 800)
    }).catch((err) => {
      wx.showToast({ title: err.error || '提交失败', icon: 'none' })
    }).finally(() => this.setData({ submitting: false }))
  }
})
