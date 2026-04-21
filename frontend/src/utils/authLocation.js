export function getPublicAuthState() {
  if (typeof window === 'undefined') {
    return {
      view: 'login',
      resetToken: '',
    }
  }

  const searchParams = new URLSearchParams(window.location.search)
  const authView = searchParams.get('auth')

  if (authView === 'register') {
    return {
      view: 'register',
      resetToken: '',
    }
  }

  if (authView === 'forgot-password') {
    return {
      view: 'forgot-password',
      resetToken: '',
    }
  }

  if (authView === 'reset-password') {
    return {
      view: 'reset-password',
      resetToken: searchParams.get('token') ?? '',
    }
  }

  return {
    view: 'login',
    resetToken: '',
  }
}

export function replacePublicAuthState(view, resetToken = '') {
  if (typeof window === 'undefined') {
    return
  }

  const nextUrl = new URL(window.location.href)

  if (view === 'login') {
    nextUrl.searchParams.delete('auth')
    nextUrl.searchParams.delete('token')
  } else {
    nextUrl.searchParams.set('auth', view)
    if (view === 'reset-password' && resetToken) {
      nextUrl.searchParams.set('token', resetToken)
    } else {
      nextUrl.searchParams.delete('token')
    }
  }

  window.history.replaceState(null, '', `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`)
}
