# FIBRITO — Asistente Nutricional Adaptativo

> Planificación nutricional personalizada con ajuste automático basado en progreso real.

Fibrito es una aplicación web que genera dietas personalizadas, hace seguimiento semanal del peso corporal y ajusta automáticamente las calorías objetivo cuando detecta desviaciones respecto al plan, sin que el usuario necesite conocimientos previos de nutrición.

A diferencia de las apps de registro pasivo (MyFitnessPal, Cronometer), Fibrito actúa como un sistema de soporte activo a la decisión: analiza tendencias, evalúa la fiabilidad del seguimiento y toma decisiones de ajuste de forma autónoma.

---

## Índice

- [Características principales](#características-principales)
- [Stack tecnológico](#stack-tecnológico)
- [Arquitectura](#arquitectura)
- [Puesta en marcha](#puesta-en-marcha)
- [Variables de entorno](#variables-de-entorno)
- [Endpoints de la API](#endpoints-de-la-api)
- [Algoritmos clave](#algoritmos-clave)
- [Estructura del repositorio](#estructura-del-repositorio)

---

## Características principales

- **Cálculo metabólico** — BMR mediante la ecuación de Mifflin-St Jeor + TDEE según días de entrenamiento semanales.
- **Generación automática de dietas** — Sistema de plantillas culinarias (MealBlueprints) con solver híbrido de ajuste de porciones por resolución de sistemas lineales.
- **Seguimiento semanal de peso** — Medias semanales en ayunas para filtrar el ruido de fluctuaciones diarias (hidratación, digestión, retención de líquidos).
- **Ajuste automático de calorías** — Algoritmo condicionado por un factor de confianza (adherencia × cobertura) que evita ajustes sobre datos poco representativos.
- **Flexibilidad manual** — El usuario puede crear dietas propias, regenerar comidas individuales y sustituir alimentos respetando la estructura nutricional.
- **Dashboard de progreso** — Evolución del peso, proyección futura por regresión lineal y historial de decisiones del sistema.
- **Recuperación de contraseña** — Flujo completo con token de un solo uso y envío por SMTP.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Frontend | React + Vite + Tailwind CSS |
| Backend | Python + FastAPI + Uvicorn |
| Base de datos | MongoDB (Atlas en producción) |
| Autenticación | JWT |
| Email | SMTP (Mailtrap en desarrollo) |
| API externa | Spoonacular (datos nutricionales) |
| Contenedores | Docker + Docker Compose |
| Despliegue | Render (frontend + backend independientes) |

---

## Arquitectura

El sistema sigue una arquitectura cliente-servidor desacoplada mediante REST API. El backend se organiza en tres capas con responsabilidades bien definidas:

```
Frontend (React)
      │
      │  HTTP + JWT
      ▼
Router  ──►  Service (lógica de negocio)  ──►  Model / MongoDB
```

**Colecciones en MongoDB:**

| Colección | Contenido |
|---|---|
| `users` | Perfil, datos biométricos y objetivo nutricional |
| `diets` | Planificaciones generadas o creadas manualmente |
| `weight_logs` | Registros diarios de peso en ayunas |
| `foods_catalog` | Catálogo enriquecido vía Spoonacular |
| `diet_adherence` | Comidas marcadas como completadas, modificadas u omitidas |

**Routers definidos:**

| Router | Responsabilidad |
|---|---|
| `auth_router` | Registro, login JWT y recuperación de contraseña |
| `users_router` | Gestión de perfil y objetivos nutricionales |
| `diets_router` | Generación, modificación y sustitución de comidas |
| `progress_router` | Análisis semanal y ajuste automático de calorías |
| `adherence_router` | Registro y cálculo de adherencia a la dieta |

---

## Puesta en marcha

El proyecto se puede ejecutar de dos formas según la fase de desarrollo.

### Producción — Render (recomendado)

La aplicación está desplegada en Render con integración continua con GitHub: cualquier push a la rama principal actualiza automáticamente el entorno de producción, lo que durante las fases finales permitió recoger feedback de usuarios reales sin fricciones de despliegue.

**URL pública:** [https://fibrito-frontend.onrender.com](https://fibrito-frontend.onrender.com)

El frontend y el backend se despliegan como servicios independientes en Render, con MongoDB Atlas como base de datos externa y las variables de entorno configuradas desde el panel de Render.

### Desarrollo local — Docker

Para ejecutar el proyecto en local durante el desarrollo se utilizó Docker Compose. Las credenciales y claves necesarias (JWT, SMTP, MongoDB, Spoonacular) se gestionaron a través de un archivo `.env` excluido del repositorio para evitar exponer información sensible. El archivo `.env.example` incluido en el repo documenta todas las variables necesarias (ver [Variables de entorno](#variables-de-entorno)).

---

## Variables de entorno

| Variable | Descripción | Requerida |
|---|---|---|
| `JWT_SECRET_KEY` | Clave secreta para firmar tokens JWT | ✅ |
| `SMTP_HOST` | Servidor SMTP para envío de emails | ✅ |
| `SMTP_PORT` | Puerto del servidor SMTP | ✅ |
| `SMTP_FROM_EMAIL` | Dirección de origen de los emails | ✅ |
| `SMTP_USERNAME` | Usuario SMTP (si requiere autenticación) | Opcional |
| `SMTP_PASSWORD` | Contraseña SMTP (si requiere autenticación) | Opcional |
| `SPOONACULAR_API_KEY` | API key de Spoonacular para datos nutricionales | ✅ |
| `MONGODB_URI` | URI de conexión a MongoDB | ✅ |

> Para desarrollo local con Mailtrap, usar las credenciales del sandbox gratuito disponibles en el dashboard de Mailtrap.

---

## Endpoints de la API

### Autenticación

```
POST  /auth/register          Registro de nuevo usuario
POST  /auth/login             Login y obtención de token JWT
POST  /auth/forgot-password   Solicitud de recuperación de contraseña
POST  /auth/reset-password    Confirmación y cambio de contraseña
```

### Usuario

```
GET   /users/me               Perfil y datos del usuario autenticado
PUT   /users/me               Actualización de perfil y preferencias
```

### Dietas

```
POST  /diets/generate         Generación automática de dieta personalizada
GET   /diets/                 Listado de dietas del usuario
PUT   /diets/{id}             Modificación de dieta existente
POST  /diets/{id}/regenerate  Regeneración de una comida individual
POST  /diets/{id}/substitute  Sustitución de un alimento dentro de una comida
```

### Progreso

```
POST  /progress/weight        Registro de peso diario en ayunas
GET   /progress/summary       Resumen semanal y factor de confianza
GET   /progress/history       Historial de análisis y ajustes realizados
```

### Adherencia

```
POST  /adherence/log          Marcar comida como completada, modificada u omitida
GET   /adherence/weekly       Adherencia y cobertura de la semana actual
```

---

## Algoritmos clave

### Cálculo metabólico

El BMR se estima con la ecuación de Mifflin-St Jeor:

```
BMR = 10·peso + 6.25·altura − 5·edad + s
  donde s = +5 (hombre) | s = −161 (mujer)

TDEE = BMR × factor_actividad  (1.2 – 1.725 según días de entrenamiento)

Calorías objetivo:
  Perder grasa  →  TDEE × 0.85
  Mantenimiento →  TDEE × 1.00
  Ganar masa    →  TDEE × 1.12
```

### Ajuste de porciones (solver híbrido)

El ajuste de cantidades se formula como un sistema lineal `Ax = t`, donde `A` es la matriz de composición nutricional por gramo y `t` es el vector de macronutrientes objetivo.

- **Fase 1** — Solución exacta dentro de los rangos de cantidad por rol nutricional.
- **Fase 2** — Si no existe solución exacta válida, refinamiento iterativo sobre el residual `r = t − Ax` con factores de escala `α ∈ {1.0, 0.75, 0.5, 0.25, 0.1}`, máximo 10 iteraciones.

Tolerancias de validación: ±10 kcal · ±1 g por macronutriente.

### Ajuste automático de calorías

El sistema compara medias semanales de peso en ayunas y aplica ajustes condicionados al factor de confianza:

```
adherencia  = puntuación_total / comidas_registradas
cobertura   = comidas_registradas / comidas_planificadas
confianza   = adherencia × cobertura

Si confianza < 0.60 → sin ajuste (datos insuficientes)
```

| Objetivo | Situación | Ajuste |
|---|---|---|
| Ganar masa | Bajada de peso | +150 kcal |
| Ganar masa | Subida demasiado rápida | −100 kcal |
| Perder grasa | Subida de peso | −150 kcal |
| Perder grasa | Bajada > 1 % peso/semana | +100 kcal |
| Perder grasa | Bajada < 0.5 % peso/semana | −100 kcal |
| Mantenimiento | Cambio > +0.15 kg/semana | −100 kcal |
| Mantenimiento | Cambio < −0.15 kg/semana | +100 kcal |

---

## Estructura del repositorio

```
fibrito/
├── frontend/                  # Cliente React
│   ├── src/
│   │   ├── components/        # Componentes reutilizables
│   │   ├── pages/             # Vistas principales (Dashboard, Dietas, Progreso, Perfil)
│   │   └── context/           # AuthContext y estado global
│   └── vite.config.js
│
├── backend/                   # API FastAPI
│   └── app/
│       ├── routes/            # Routers (auth, users, diets, progress, adherence)
│       ├── services/          # Lógica de negocio y algoritmos
│       ├── models/            # Esquemas Pydantic y acceso a MongoDB
│       └── main.py            # Punto de entrada FastAPI
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Tests

Las pruebas automatizadas se ejecutan con `pytest` desde el directorio `backend/`:

```bash
pytest tests/
```

Cobertura principal:

| Archivo | Qué verifica |
|---|---|
| `test_generate_diet.py` | Generación completa y coherencia nutricional |
| `test_regeneration.py` | Regeneración de comidas con variedad y restricciones |
| `test_substitution.py` | Sustitución de alimentos y reajuste de macros |
| `test_allergy_hard_constraints.py` | Alergias e intolerancias nunca aparecen en las comidas |
| `test_preferred_foods.py` | Priorización de alimentos preferidos |
| `test_adherence.py` | Cálculo de adherencia, cobertura y fiabilidad |
| `test_active_diet.py` | Activación y selección correcta de dietas |
| `test_dashboard.py` | Coherencia de los datos mostrados al usuario |

---

## Licencia

Proyecto académico — Trabajo Fin de Grado en Ingeniería Informática, CUNEF Universidad (2025-2026).