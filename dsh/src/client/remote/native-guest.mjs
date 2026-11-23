export function remoteUrl(value) {
  let url
  try { url = new URL(value) } catch { throw new Error('远程工作台地址无效，请重新连接。') }
  if (!/^https?:$/.test(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.username || url.password) {
    throw new Error('远程工作台必须使用本机 SSH 隧道地址，请重新连接。')
  }
  return url.href
}

export function desktopBrowser() {
  const desktop = window.dshDesktop
  if (desktop?.protocolVersion !== 1 || typeof desktop.browser?.acquire !== 'function' || typeof desktop.browser?.release !== 'function') {
    throw new Error('当前环境不支持 DSH 原生内嵌浏览器，请使用桌面版 DSH。')
  }
  return desktop.browser
}

// This is the same approved lease protocol used by DSH's built-in Browser.
// The main process supplies the partition and enforces the guest sandbox.
export function createNativeGuest(options) {
  const bridge = options.bridge
  const host = options.host
  const target = remoteUrl(options.url)
  const origin = new URL(target).origin
  const pathname = new URL(target).pathname
  const lifetime = new AbortController()
  let disposed = false
  let element = null
  let lease = null
  let ready = false
  let initialNavigation = false
  let loadFailed = false
  let unsubscribeOpen = null
  let timeout = null
  let disposal = null
  const releases = new Map()
  function report(value) { if (!disposed) options.onState?.(value) }
  let lastCreation = null
  function observeLocation(inPage = false) {
    if (disposed || !ready || !initialNavigation || !element) return
    try {
      const address = new URL(element.getURL())
      if (address.origin !== origin || address.pathname !== pathname || address.username || address.password) return
      const params = new URLSearchParams(address.hash.slice(1))
      if (params.get('cannEmbed') !== '1' || params.get('cannMode') !== 'cannbot') return
      const creation = params.get('cannNewFolder')
      if (inPage && creation && /^[a-f0-9-]{36}$/i.test(creation) && creation !== lastCreation) {
        lastCreation = creation; options.onCreateWorkspace?.()
      }
      const workspaceId = params.get('cannWorkspace') || undefined
      const sessionId = params.get('cannSession') || undefined
      if ([workspaceId, sessionId].some(value => value && (value.length > 512 || /[\u0000-\u0020]/.test(value)))) return
      if (sessionId && !workspaceId) return
      // Only opaque workspace/session IDs leave the guest; never its auth URL.
      options.onLocation?.({ workspaceId, sessionId })
    } catch { /* Ignore unrelated or partially committed navigation. */ }
  }
  function clearTimer() { if (timeout !== null) { clearTimeout(timeout); timeout = null } }
  function failed() {
    loadFailed = true
    clearTimer()
    report({ status: 'error', error: '远端页面加载失败，请检查连接后重试。' })
  }
  function loading() {
    loadFailed = false
    clearTimer()
    report({ status: 'loading', error: '', notice: '' })
    timeout = setTimeout(failed, 30_000)
  }
  function release(id) {
    if (!id) return Promise.resolve()
    if (!releases.has(id)) releases.set(id, Promise.resolve().then(function () { return bridge.release(id) }).catch(function () {
      // IPC exceptions can carry addresses. Keep them out of logs and UI.
    }))
    return releases.get(id)
  }
  function removeGuest() {
    clearTimer()
    lifetime.abort()
    if (unsubscribeOpen) { try { unsubscribeOpen() } catch {} unsubscribeOpen = null }
    if (element) { element.remove(); element = null }
    ready = false
    return release(lease)
  }
  function navigate(url) {
    if (disposed || !ready || !element) return
    loading()
    try {
      Promise.resolve(element.loadURL(url)).catch(function (error) {
        if (!disposed && error?.code !== 'ERR_ABORTED') failed()
      })
    } catch { failed() }
  }
  loading()
  const initializing = Promise.resolve().then(function () {
    return bridge.acquire(options.workspaceKey)
  }).then(async function (reservation) {
    if (reservation && typeof reservation.lease === 'string' && reservation.lease) lease = reservation.lease
    if (!reservation || typeof reservation.lease !== 'string' || !reservation.lease
      || typeof reservation.partition !== 'string' || !reservation.partition) throw new Error('invalid reservation')
    if (disposed) { await release(reservation.lease); return }
    const ownerDocument = host.ownerDocument || document
    element = ownerDocument.createElement('webview')
    element.dataset.sidebarBrowserFrame = 'webview'
    element.setAttribute('aria-label', '远端 DSH 工作台')
    element.setAttribute('name', lease)
    element.setAttribute('partition', reservation.partition)
    element.setAttribute('allowpopups', '')
    element.setAttribute('src', 'about:blank#' + lease)
    Object.assign(element.style, { width: '100%', height: '100%', display: 'flex', border: '0' })
    const listen = function (name, listener) { element.addEventListener(name, listener, { signal: lifetime.signal }) }
    listen('dom-ready', function () {
      if (disposed) return
      ready = true
      if (!initialNavigation) { initialNavigation = true; navigate(target) }
    })
    listen('did-start-loading', function () { if (initialNavigation) loading() })
    listen('did-finish-load', function () {
      if (!initialNavigation || disposed) return
      try { if (element.getURL().startsWith('about:')) return } catch { return }
      clearTimer()
      report({ status: 'ready', error: '' })
      observeLocation()
    })
    listen('did-navigate-in-page', function (event) {
      if (!event.isMainFrame || !initialNavigation || disposed || !ready) return
      observeLocation(true)
      clearTimer()
      report({ status: 'ready', error: '' })
    })
    listen('did-stop-loading', function () {
      if (!initialNavigation || disposed || !ready || loadFailed) return
      try { if (element.getURL().startsWith('about:')) return } catch { return }
      clearTimer()
      report({ status: 'ready', error: '' })
      observeLocation()
    })
    listen('did-fail-load', function (event) {
      if (event.isMainFrame && event.errorCode !== -3) failed()
    })
    listen('render-process-gone', failed)
    if (typeof bridge.onOpenRequested === 'function') {
      unsubscribeOpen = bridge.onOpenRequested(lease, function (value) {
        if (disposed) return
        let url
        try { url = new URL(value) } catch { return }
        if (url.origin === origin && !url.username && !url.password) navigate(url.href)
        else report({ notice: '此链接指向其他站点，当前工作区保留在远端服务器页面。' })
      })
    }
    host.append(element)
  }).catch(function () {
    if (!disposed) failed()
    return removeGuest()
  })
  return {
    reload: function () {
      if (disposed || !ready || !element) return false
      loading()
      try { element.reload(); return true } catch { failed(); return false }
    },
    dispose: function () {
      if (disposal) return disposal
      disposed = true
      const pendingRelease = removeGuest()
      disposal = Promise.all([pendingRelease, initializing]).then(function () { return Promise.all(releases.values()) }).then(function () {})
      return disposal
    },
  }
}
