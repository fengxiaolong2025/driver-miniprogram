// 后端 API 配置
// 开发调试：微信开发者工具 → 详情 → 本地设置 → 勾选「不校验合法域名」
// 真机调试：改为电脑局域网 IP，如 http://192.168.1.100:8081
// 正式发布（腾讯云 CloudBase 云托管）：改为云托管 HTTPS 域名，见 CLOUD_DEPLOY.md §4/§6
//   const BASE_URL = 'https://driver-api-xxxx.ap-shanghai.run.tcloudbase.com'
const BASE_URL = 'http://127.0.0.1:8081'

function getToken() {
  return wx.getStorageSync('token') || ''
}

function request(path, method, data) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: BASE_URL + path,
      method: method || 'GET',
      data: data || {},
      header: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + getToken()
      },
      success(res) {
        if (res.statusCode === 200 && res.data && res.data.ok) {
          resolve(res.data.data)
        } else if (res.statusCode === 401) {
          wx.removeStorageSync('token')
          wx.removeStorageSync('user')
          reject({ needLogin: true, error: res.data.error || '登录已过期' })
        } else {
          reject({ error: (res.data && res.data.error) || '请求失败(' + res.statusCode + ')' })
        }
      },
      fail() {
        reject({ error: '网络请求失败，请检查后端服务' })
      }
    })
  })
}

function upload(path, filePath, formData) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: BASE_URL + path,
      filePath: filePath,
      name: 'photo',
      formData: formData || {},
      header: { 'Authorization': 'Bearer ' + getToken() },
      success(res) {
        try {
          const data = JSON.parse(res.data)
          if (data.ok) resolve(data.data)
          else reject({ error: data.error || '上传失败' })
        } catch (e) {
          reject({ error: '上传响应异常' })
        }
      },
      fail() {
        reject({ error: '上传失败，请检查网络' })
      }
    })
  })
}

module.exports = {
  BASE_URL,
  getToken,
  request,
  upload
}
