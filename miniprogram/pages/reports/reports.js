const app = getApp()
const api = require('../../utils/api')

const TABS = [
  { key: 'trips', label: '出车报表', groupOpts: ['日期', '人员', '车辆', '出发地', '目的地'], groupKeys: ['trip_date', 'name', 'plate', 'origin', 'destination'] },
  { key: 'refuels', label: '加油报表', groupOpts: ['日期', '人员', '车辆'], groupKeys: ['refuel_date', 'name', 'plate'] },
  { key: 'maintenances', label: '保养报表', groupOpts: ['日期', '人员', '车辆'], groupKeys: ['maintain_time', 'name', 'plate'] }
]

Page({
  data: {
    tabs: TABS.map((t) => t.label),
    tab: 0,
    from: '',
    to: '',
    today: '',
    groupOpts: TABS[0].groupOpts,
    groupIndex: 0,
    loading: false,
    // 出车
    tripSummary: null,
    tripGroup: [],
    tripDetail: [],
    // 加油
    fuelSummary: null,
    fuelGroup: [],
    fuelDetail: [],
    // 保养
    maintSummary: null,
    maintGroup: [],
    maintDetail: [],
    photoBase: api.BASE_URL + '/uploads/'
  },

  onLoad() {
    const now = new Date()
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1)
    this.setData({
      from: this.fmtDate(firstDay),
      to: this.fmtDate(now),
      today: this.fmtDate(now)
    })
    this.load()
  },

  fmtDate(d) {
    const p = (n) => (n < 10 ? '0' + n : '' + n)
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
  },

  onTab(e) {
    const tab = +e.currentTarget.dataset.index
    this.setData({
      tab,
      groupOpts: TABS[tab].groupOpts,
      groupIndex: 0
    })
    this.load()
  },

  onGroupChange(e) {
    this.setData({ groupIndex: +e.detail.value })
    this.load()
  },

  onFrom(e) { this.setData({ from: e.detail.value }); this.load() },
  onTo(e) { this.setData({ to: e.detail.value }); this.load() },

  load() {
    const { tab, from, to, groupIndex } = this.data
    const t = TABS[tab]
    const groupKey = t.groupKeys[groupIndex]
    this.setData({ loading: true })
    api.request('/api/reports/' + t.key, 'GET', { from, to, group_by: groupKey })
      .then((data) => {
        const patch = { loading: false }
        if (t.key === 'trips') {
          patch.tripSummary = { total: data.summary.total }
          patch.tripGroup = data.group
          patch.tripDetail = data.detail
        } else if (t.key === 'refuels') {
          const s = data.summary
          patch.fuelSummary = {
            cnt: s.cnt,
            total_amount: this.num(s.total_amount),
            total_liters: this.num(s.total_liters, 1),
            avg_price: this.num(s.avg_price, 2),
            avg_fuel: this.num(s.avg_fuel, 2)
          }
          patch.fuelGroup = data.group
          patch.fuelDetail = data.detail
        } else {
          patch.maintSummary = { cnt: data.summary.cnt, total_cost: this.num(data.summary.total_cost) }
          patch.maintGroup = data.group
          patch.maintDetail = data.detail
        }
        this.setData(patch)
      })
      .catch((err) => {
        this.setData({ loading: false })
        wx.showToast({ title: err.error || '加载失败', icon: 'none' })
      })
  },

  num(v, digits) {
    const n = parseFloat(v) || 0
    return typeof digits === 'number' ? +n.toFixed(digits) : Math.round(n)
  },

  // 明细照片预览
  previewPhoto(e) {
    const src = e.currentTarget.dataset.src
    if (src) wx.previewImage({ urls: [src] })
  },

  // 导出当前报表为 Excel
  exportExcel() {
    const { tab, from, to } = this.data
    const t = TABS[tab]
    const url = api.BASE_URL + '/api/export/' + t.key + '?from=' + from + '&to=' + to
    wx.showLoading({ title: '正在生成...', mask: true })
    wx.downloadFile({
      url,
      header: { 'Authorization': 'Bearer ' + api.getToken() },
      success(res) {
        wx.hideLoading()
        if (res.statusCode !== 200) {
          let msg = '导出失败(' + res.statusCode + ')'
          try { msg = JSON.parse(res.data).error || msg } catch (e) { /* 忽略 */ }
          wx.showToast({ title: msg, icon: 'none' })
          return
        }
        wx.openDocument({
          filePath: res.tempFilePath,
          fileType: 'xlsx',
          showMenu: true,
          fail() {
            wx.showToast({ title: '文件打开失败', icon: 'none' })
          }
        })
      },
      fail() {
        wx.hideLoading()
        wx.showToast({ title: '下载失败，请检查网络', icon: 'none' })
      }
    })
  }
})
