# Design System Strategy: Technical Precision & Athletic Depth

## 1. Overview & Creative North Star
**The Creative North Star: "The Kinetic Lab"**

This design system is engineered to feel like a high-performance laboratory—precise, technical, and hyper-efficient. We are moving away from the "standard app" aesthetic toward a **High-End Editorial Technical** experience. The layout rejects the rigidity of common mobile grids in favor of **Intentional Asymmetry**. 

By utilizing heavy-weight typography against deep, translucent layers, we create a sense of "Athletic Depth." The UI should feel like a premium piece of sports equipment: lightweight but incredibly strong. We achieve this through "breathing room" (generous white space), overlapping technical data visualizations, and a rejection of traditional structural containment.

---

## 2. Colors & Surface Architecture
The color palette is built on a foundation of absolute darkness, punctuated by high-visibility "Athletic Neon."

### The Color Logic
- **Primary Foundation:** `#0e0e0f` (Background). This isn't just black; it’s a deep, obsidian base that allows neon accents to vibrate.
- **Action Neon:** `#daf900` (Primary Container). Used sparingly for high-intent actions.
- **Alert Red:** `#ff7162` (Tertiary). Reserved for critical calorie adjustments or performance drops.

### The "No-Line" Rule
To maintain a premium feel, **1px solid borders are prohibited for sectioning.** We define boundaries through tonal shifts. 
- Use `surface-container-low` (#131314) for large background sections.
- Use `surface-container-high` (#201f21) for interactive elements within those sections.
- Transitioning between these tones provides a sophisticated, "borderless" containment that feels more modern and integrated.

### The "Glass & Gradient" Rule
To prevent the dark theme from feeling "flat" or "muddy," all floating modals and navigation bars must utilize **Glassmorphism**:
- **Token:** `surface-variant` (#262627) at 60% opacity.
- **Effect:** 20px - 40px Backdrop Blur.
- **Signature Texture:** For primary CTAs, do not use flat colors. Use a subtle linear gradient from `primary` (#f6ffc0) to `primary-container` (#daf900) at a 135-degree angle to provide a metallic, high-performance sheen.

---

## 3. Typography
We utilize a pairing of **Space Grotesk** (for technical authority) and **Inter** (for high-readability data).

| Level | Token | Font | Size | Character |
| :--- | :--- | :--- | :--- | :--- |
| **Display** | `display-lg` | Space Grotesk | 3.5rem | Bold, technical, aggressive tracking (-2%) |
| **Headline** | `headline-md` | Space Grotesk | 1.75rem | Authoritative, used for section starts |
| **Title** | `title-lg` | Inter | 1.375rem | Medium weight, high legibility for metrics |
| **Body** | `body-md` | Inter | 0.875rem | Regular weight, optimized for nutrition facts |
| **Label** | `label-sm` | Inter | 0.6875rem | All-caps, +5% tracking for "technical" feel |

**Editorial Note:** Use `display-lg` for macro-nutrient numbers (e.g., "180g Protein") to create a high-contrast hierarchy that feels like a sports magazine spread.

---

## 4. Elevation & Depth
Depth in this system is achieved through **Tonal Layering** rather than traditional drop shadows.

- **The Layering Principle:** Stack `surface-container-lowest` (#000000) cards on a `surface-container-low` (#131314) background. This "sunken" effect creates a natural focus area without adding visual noise.
- **Ambient Shadows:** For floating action buttons or high-priority modals, use a "Neon Glow" shadow. Instead of black, use a 4% opacity version of the `primary` token with a 60px blur. This mimics the ambient light of a technical screen.
- **The "Ghost Border" Fallback:** If a border is required for accessibility on inputs, use `outline-variant` (#484849) at **15% opacity**. It should be felt, not seen.

---

## 5. Components

### Buttons
- **Primary:** Gradient fill (`primary` to `primary-container`), black text (`on_primary`), `0.375rem` (md) radius.
- **Secondary:** Ghost style. No fill, `outline-variant` at 20% opacity, white text.
- **Tertiary:** Text only, `label-md` styling, `primary` color.

### Technical Cards
- **Rule:** Forbid divider lines. 
- Use `spacing-xl` (vertical white space) to separate content.
- Cards should use `surface-container-highest` (#262627) with a subtle `0.5rem` (lg) corner radius. 
- Apply a `0.125rem` (sm) top-stroke in `primary` to "highlight" active performance cards.

### Input Fields
- **Base:** `surface-container-lowest` (#000000).
- **Active State:** A bottom-only border of 2px using the `primary` (#f6ffc0) token.
- **Error:** Shift the bottom border to `error` (#ff7351); no "shaking" animations—keep it professional and static.

### Data Visualization (The "Performance Gauge")
- Use `primary-dim` (#d0ed00) for progress bars. 
- Use thin, 2px stroke weights for all charts to maintain the "technical lab" aesthetic. 
- Background tracks for gauges must use `surface-bright` (#2c2c2d) to ensure the neon "pops."

---

## 6. Do's and Don'ts

### Do:
- **Do** use intentional asymmetry. Align large display type to the left while keeping data points right-aligned.
- **Do** use "Optical Spacing." If a card has a neon accent, increase the padding around it to let the color breathe.
- **Do** use high-quality, desaturated imagery. Photos of food or athletes should have lower saturation to ensure the `primary` neon remains the focal point.

### Don't:
- **Don't** use pure white (#FFFFFF) for body text. Use `on_surface_variant` (#adaaab) to reduce eye strain in the dark environment.
- **Don't** use standard 1px dividers. If you need to separate items in a list, use a change in background tone or a 16px gap.
- **Don't** use rounded "pill" buttons for everything. Stick to the `0.375rem` (md) radius to maintain a technical, "machined" look.