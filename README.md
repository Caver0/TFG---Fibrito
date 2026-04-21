# FIBRITO

Aplicacion web para la planificacion nutricional personalizada y el seguimiento adaptativo del progreso corporal.

## Stack principal

- Frontend: React + Vite
- Backend: FastAPI
- Base de datos: MongoDB
- Contenedores: Docker Compose

## Estructura general

- `frontend/`: cliente web
- `backend/`: API y logica de negocio
- `docker-compose.yml`: orquestacion local del proyecto

## Primer arranque

### 1. Crear archivo `.env`

Copiar `.env.example` a `.env` y completar:

- `JWT_SECRET_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_FROM_EMAIL`
- `SMTP_USERNAME` y `SMTP_PASSWORD` si tu servidor SMTP requiere autenticacion

### 2. Levantar contenedores

```bash
docker compose up --build
```

## Autenticacion disponible

### Endpoints

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `GET /users/me`

### Recuperacion de contrasena

1. El usuario solicita recuperacion desde la pantalla de login.
2. El backend genera un token temporal distinto del JWT de sesion.
3. En Mongo solo se guarda el hash del token, junto con expiracion y fecha de solicitud.
4. El backend envia un email SMTP con un enlace al frontend.
5. El frontend abre la vista de reset usando `?auth=reset-password&token=...`.
6. Al confirmar la nueva contrasena, el token se invalida y no puede reutilizarse.

## Prueba local rapida

1. Configura `.env`.
2. Arranca `docker compose up --build`.
3. Entra en `http://localhost:5173`.
4. Prueba registro/login clasico.
5. Prueba "Recuperar contrasena" con un SMTP valido.
