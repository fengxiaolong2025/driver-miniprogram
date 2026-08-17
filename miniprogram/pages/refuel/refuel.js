const app = getApp()
const api = require('../../utils/api')

Page({
  data: {
    refuelDate: '',
    today: '',
    odometer: '',
    travelKm: '',
    oilPrice: '',
    liters: '',
    amount: '',
    fuel: '',
    vehicles: [],
    vehIndex: -1,
    submitting: false
  },

  onLoad() {
    this.setData({ refuelDate: this.fmtDate(new Date()), today: this.fmtDate(new Date()) })
    app.loadOptions()
      .then((opt) => {
        this.setData({ vehicles: (opt.vehicles || []).map((v) => v.plate) })
      })
      .catch(() => {})
  },

  fmtDate(d) {
    const p = (n) => (n < 10 ? '0' + n : '' + n)
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
  },

  onDate(e) { this.setData({ refuelDate: e.detail.value }) },
  onOdo(e) { this.setData({ odometer: e.detail.value }) },
  onTravel(e) { this.setData({ travelKm: e.detail.value }) },
  onPrice(e) { this.setData({ oilPrice: e.detail.value }) },
  onLiters(e) { this.setData({ liters: e.detail.value }) },
  onAmount(e) { this.setData({ amount: e.detail.value }) },
  onFuel(e) { this.setData({ fuel: e.detail.value }) },
  onVeh(e) { this.setData({ vehIndex: +e.detail.value }) },

  onSubmit() {
    const d = this.data
    if (!d.travelKm && !d.amount && !d.liters) {
      return wx.showToast({ title: '请至少填写行驶公里、加油量或金额', icon: 'none' })
    }
    this.setData({ submitting: true })
    api.request('/api/refuels', 'POST', {
      refuel_date: d.refuelDate,
      odometer: d.odometer || 0,
      travel_km: d.travelKm || 0,
      oil_price: d.oilPrice || 0,
      liters: d.liters || 0,
      amount: d.amount || 0,
      fuel_consumption: d.fuel || 0,
      plate: d.vehIndex >= 0 ? d.vehicles[d.vehIndex] : ''
    }).then(() => {
      wx.showToast({ title: '加油记录已提交', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 800)
    }).catch((err) => {
      wx.showToast({ title: err.error || '提交失败', icon: 'none' })
    }).finally(() => this.setData({ submitting: false }))
  }
})
