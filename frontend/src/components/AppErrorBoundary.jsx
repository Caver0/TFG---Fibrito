import { Component } from 'react'

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = {
      error: null,
    }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error) {
    if (typeof window !== 'undefined') {
      console.error('FIBRITO render error:', error)
    }
  }

  handleReset = () => {
    try {
      window.localStorage.removeItem('fibrito-auth')
    } catch {
      // Ignoramos bloqueos de storage y forzamos recarga igualmente.
    }

    window.location.hash = ''
    window.location.reload()
  }

  render() {
    const { error } = this.state
    const { children } = this.props

    if (!error) {
      return children
    }

    return (
      <main className="app-shell app-shell-auth">
        <section className="auth-stage">
          <section className="auth-panel app-error-panel">
            <div className="auth-copy">
              <span className="eyebrow">Render error</span>
              <h1>La interfaz se ha bloqueado al cargar</h1>
              <p>
                Hemos evitado que la app se quede en blanco. Lo mas probable es
                que haya una sesion guardada o un dato del dashboard que este
                provocando el fallo al renderizar.
              </p>
            </div>

            <div className="info-note info-note-warning">
              {error.message || 'Error de render no identificado.'}
            </div>

            <button type="button" onClick={this.handleReset}>
              Limpiar sesion local y recargar
            </button>
          </section>
        </section>
      </main>
    )
  }
}

export default AppErrorBoundary
