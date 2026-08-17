const app = getApp()
const api = require('../../utils/api')

Page({
  data: {
    date: '',
    time: '',
    today: '',
    photoPath: '',
    items: '',
    cost: '',
    remark: '',
    vehicles: [],
    vehIndex: -1,
    submitting: false
  },

  onLoad() {
    const now = new Date()
    this.setData({
      date: this.fmtDate(now),
      time: this.fmtTime(now),
      today: this.fmtDate(now)
    })
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

  fmtTime(d) {
    const p = (n) => (n < 10 ? '0' + n : '' + n)
    return p(d.getHours()) + ':' + p(d.getMinutes())
  },

  onDate(e) { this.setData({ date: e.detail.value }) },
  onTime(e) { this.setData({ time: e.detail.value }) },
  onItems(e) { this.setData({ items: e.detail.value }) },
  onCost(e) { this.setData({ cost: e.detail.value }) },
  onRemark(e) { this.setData({ remark: e.detail.value }) },
  onVeh(e) { this.setData({ vehIndex: +e.detail.value }) },

  // 拍照 / 选择照片
  onChoosePhoto() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      sizeType: ['compressed'],
      success: (res) => {
        if (res.tempFiles && res.tempFiles.length > 0) {
          this.setData({ photoPath: res.tempFiles[0].tempFilePath })
        }
      }
    })
  },

  onRemovePhoto() {
    this.setData({ photoPath: '' })
  },

  onSubmit() {
    const d = this.data
    if (!d.items && !d.cost && !d.photoPath) {
      return wx.showToast({ title: '请填写保养项目、费用或上传照片', icon: 'none' })
    }
    this.setData({ submitting: true })

    const formData = {
      maintain_time: d.date + ' ' + d.time,
      items: d.items,
      cost: d.cost || 0,
      remark: d.remark,
      plate: d.vehIndex >= 0 ? d.vehicles[d.vehIndex] : ''
    }

    const doSubmit = (path) => {
      if (path) {
        return api.upload('/api/maintenances', path, formData)
      }
      return api.request('/api/maintenances', 'POST', formData)
    }

    doSubmit(d.photoPath)
      .then(() => {
        wx.showToast({ title: '保养记录已提交', icon: 'success' })
        setTimeout(() => wx.navigateBack(), 800)
      })
      .catch((err) => {
        wx.showToast({ title: err.error || '提交失败', icon: 'none' })
      })
      .finally(() => this.setData({ submitting: false }))
  }
})
