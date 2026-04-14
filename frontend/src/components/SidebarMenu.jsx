import { useEffect, useState } from 'react'

const SECTIONS = [
  {
    id: 'panel-dashboard',
    label: 'Dashboard',
    description: 'Resumen y progreso',
  },
  {
    id: 'panel-perfil',
    label: 'Perfil',
    description: 'Datos y nutricion',
  },
  {
    id: 'panel-registro-peso',
    label: 'Registro de peso',
    description: 'Entradas e historial',
  },
  {
    id: 'panel-analisis-progreso',
    label: 'Analisis del progreso',
    description: 'Medias y reajustes',
  },
  {
    id: 'panel-generar-dietas',
    label: 'Generar dietas',
    description: 'Plan diario por alimentos',
  },
]

function SidebarMenu({ onLogout }) {
  const [activeSectionId, setActiveSectionId] = useState(SECTIONS[0].id)

  useEffect(() => {
    const sectionElements = SECTIONS
      .map((section) => document.getElementById(section.id))
      .filter(Boolean)

    if (sectionElements.length === 0) {
      return undefined
    }

    function getSectionDistance(element, focusLine) {
      const { top, bottom } = element.getBoundingClientRect()

      if (top <= focusLine && bottom >= focusLine) {
        return 0
      }

      return Math.min(Math.abs(top - focusLine), Math.abs(bottom - focusLine))
    }

    function updateActiveSection() {
      const focusLine = Math.min(window.innerHeight * 0.32, 260)
      const closestSection = sectionElements.reduce((bestMatch, element) => {
        const distance = getSectionDistance(element, focusLine)

        if (!bestMatch || distance < bestMatch.distance) {
          return { element, distance }
        }

        return bestMatch
      }, null)

      setActiveSectionId(closestSection?.element.id ?? sectionElements[0].id)
    }

    updateActiveSection()
    window.addEventListener('scroll', updateActiveSection, { passive: true })
    window.addEventListener('resize', updateActiveSection)

    return () => {
      window.removeEventListener('scroll', updateActiveSection)
      window.removeEventListener('resize', updateActiveSection)
    }
  }, [])

  function handleNavigate(event, sectionId) {
    event.preventDefault()
    const targetSection = document.getElementById(sectionId)
    if (!targetSection) {
      return
    }

    setActiveSectionId(sectionId)
    window.history.replaceState(null, '', `#${sectionId}`)
    targetSection.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  }

  return (
    <aside className="sidebar-menu">
      <div className="sidebar-menu-panel">
        <div className="sidebar-menu-heading">
          <span className="eyebrow">Indice</span>
          <h2>FIBRIT0</h2>
          <p>Accede al instante a los puntos principales de la aplicacion desde este menu lateral fijo.</p>
        </div>

        <nav className="sidebar-menu-links" aria-label="Secciones principales">
          {SECTIONS.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className={`sidebar-menu-link ${activeSectionId === section.id ? 'sidebar-menu-link-active' : ''}`}
              aria-current={activeSectionId === section.id ? 'true' : undefined}
              onClick={(event) => handleNavigate(event, section.id)}
            >
              <span className="sidebar-menu-link-line" aria-hidden="true" />
              <span className="sidebar-menu-link-copy">
                <strong>{section.label}</strong>
                <small>{section.description}</small>
              </span>
            </a>
          ))}
        </nav>

        <button type="button" className="secondary-button sidebar-menu-logout" onClick={onLogout}>
          Cerrar sesion
        </button>
      </div>
    </aside>
  )
}

export default SidebarMenu
