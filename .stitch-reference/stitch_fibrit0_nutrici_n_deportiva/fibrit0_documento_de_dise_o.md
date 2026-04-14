# FIBRIT0 - Especificaciones de Diseño Frontend

## 1. Visión General
FIBRIT0 es una plataforma de nutrición deportiva de alta precisión. La interfaz debe comunicar control, orden y rendimiento. No es una app de "bienestar" genérica, sino una herramienta de análisis para usuarios serios que buscan optimizar su composición corporal mediante datos.

## 2. Identidad Visual
- **Estética:** Dark Mode Premium.
- **Paleta de Colores:** Negro profundo (#0A0A0B), grises técnicos (#1C1C1E), acentos en verde neón atlético (#DFFF00) o azul eléctrico para acciones, y rojo sutil para alertas/ajustes.
- **Materiales:** Tarjetas con ligero desenfoque de fondo (glassmorphism), bordes finos y sombras sutiles.
- **Tipografía:** Sans-serif moderna y geométrica (tipo Inter o Montserrat) con pesos variables para marcar jerarquía.

## 3. Arquitectura de Pantallas

### A. Estructura Global
- **Layout:** Navegación lateral (Sidebar) persistente en escritorio para acceso rápido, colapsable o menú inferior en móvil.
- **Contenido:** Área central ancha, organizada en grids de múltiples columnas.

### B. Dashboard (Core)
- **Métricas:** 4-5 tarjetas superiores con datos críticos (Peso, Variación, Calorías, Adherencia).
- **Gráfico de Peso:** Gráfico de líneas suave con "Eventos de Ajuste" (puntos rojos) que indican cambios en el plan nutricional.
- **Widget de Adherencia:** Visualización circular o de barras del cumplimiento semanal.
- **Resumen de Dieta:** Desglose rápido de macros (P/C/F) y próximas comidas.

### C. Sistema de Dietas
- **Visualización:** Timeline vertical de comidas o grid de tarjetas.
- **Interacción:** Botones rápidos para 'Sustituir', 'Regenerar' o 'Marcar como Completada'.
- **Detalle:** Desglose por alimento con peso y macros específicos.

### D. Progreso y Adherencia
- **Análisis:** Comparativa entre la tendencia de peso esperada vs. real.
- **Nivel de Confianza:** Indicador visual que relaciona la adherencia con la fiabilidad de los datos de progreso.

### E. Perfil y Configuración
- **Formularios:** Grupos de inputs técnicos (Peso, Altura, BF%, TMB).
- **Preferencias:** Selectores de exclusión de alimentos y etiquetas de restricciones (Vegano, Keto, etc.).

## 4. Principios UI/UX
1. **Densidad de Información Equilibrada:** Evitar el desorden pero proporcionar todos los datos necesarios.
2. **Jerarquía Visual:** Lo más importante (peso/calorías) siempre destaca.
3. **Consistencia de Componentes:** Todos los botones, inputs y tarjetas deben pertenecer a la misma familia visual.
4. **Responsive:** Adaptación fluida desde monitores UltraWide hasta smartphones.
