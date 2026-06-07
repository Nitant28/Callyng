---
name: Aakashvani "Dual Identity"
fonts:
  headings: "Plus Jakarta Sans"
  body: "Inter"
colors:
  light: # Arctic Signal
    background: "#F5F8FF"      
    surface: "#FFFFFF"         
    primary: "#1647E8"         
    text: "#0B1840"            
    text-muted: "#6B85B5"      
    success: "#00C8AE"         
    warning: "#D48A00"         
    error: "#DC323C"           
  dark: # Molten Studio
    background: "#141210"      
    surface: "#1C1810"         
    primary: "#4D75FA"         
    text: "#FFF8EC"            
    text-muted: "#7A7060"      
    success: "#FFB932"         
    warning: "#FF7A3C"         
    error: "#FF426A"           
rounded:
  sm: 6px
  md: 8px
  lg: 16px
  pill: 9999px
---

# Design System: Aakashvani "Electric Professional"

## Overview
A dynamic, dual-theme (Light & Dark) interface built for a fast-paced, young company that refuses to look like a generic, uninspired template. 
It balances strict **professional standards** (crucial for older generation clients and enterprise trust) with **electric, vibrant accents** that reflect a high-velocity startup.

## Typography
- **Headlines (`Plus Jakarta Sans`)**: Sharp, modern, and energetic. Used for page titles, massive metric numbers, and hero elements. This font immediately injects startup personality and breaks away from generic defaults.
- **Body (`Inter`)**: The gold standard for data density. Used for data tables, transcript logs, and complex forms where extreme readability is paramount.
- **Weights**: Use `ExtraBold (800)` for top-level headers to give them punch, `Medium (500)` for table headers, and `Regular (400)` for standard data.

## Color Philosophy
The palette abandons the standard "boring SaaS grey" in favor of two extremely distinct, personality-driven themes:
* **Light Mode (Arctic Signal)**: An intensely crisp and corporate aesthetic. The icy blue-tinted `#F5F8FF` background beneath pure white `#FFFFFF` cards creates a beautiful, clean depth. The deep navy text (`#0B1840`) ensures it is perfectly legible for older or enterprise clients, looking highly trustworthy and precise.
* **Dark Mode (Molten Studio)**: Highly unexpected and sophisticated. Instead of defaulting to standard cool grays/blues, it uses a rich, warm studio aesthetic with deep amber/brown undertones (`#141210`). The primary Indigo (`#4D75FA`) pops aggressively against this warm canvas. The off-white cream text (`#FFF8EC`) makes it feel like an expensive code editor or a high-end audio engineering dashboard.
* **Status Accents**: Arctic Signal uses sharp corporate indicators (Bright Teal `#00C8AE`, Punchy Crimson `#DC323C`). Molten Studio uses glowing, high-energy accents (Warm Golden Yellow `#FFB932`, Neon Rose `#FF426A`).

## Components & "Anti-Slop" Styling (Atomic UI Kit)
To avoid looking like a generic AI-generated template, the UI relies on a reusable atomic UI kit located in `src/components/shared/ui/`. **All new screens must use these components** rather than building custom buttons or cards with utility classes.

- **`Button`**: `8px` (`rounded-lg`) border radius. Uses a subtle inner shadow (`inner-shadow-primary`) on the primary variant to make it tactile. On hover, it translates up `1px`. Supports variants (`primary`, `secondary`, `outline`, `ghost`, `danger`) and an `isLoading` prop.
- **`Card` & `DataTable`**: `8px` (`rounded-lg`) border radius. 
  - *Light Mode*: Uses a custom cool-toned drop shadow (`shadow-[0_4px_20px_rgba(22,71,232,0.05)]`) to lift the surface off the background.
  - *Dark Mode*: No drop shadows. Instead, uses a crisp 1px border (`#2A345E`) around the cards.
- **`Badge`**: Pill-shaped (`9999px`). Status badges automatically apply a 15% opacity background of their respective color with fully opaque text (e.g., "Running" uses `bg-primary/15 text-primary`).
- **`ThemeToggle`**: A ready-to-use toggle component that respects the user's local storage and system preference for switching between Arctic Signal and Molten Studio.
- **Transcript UI (Chat Bubbles)**:
  - **AI (Left)**: Subdued surface color with a 2px Indigo left-border to ground it.
  - **Human (Right)**: Solid Indigo background (light mode) or surface-elevated background (dark mode).

## Do's and Don'ts
- **Do** support a system-preference toggle for Light/Dark mode. Older clients often prefer Light mode for legibility, while devs/ops prefer Dark mode for long sessions.
- **Do** use `tabular-nums` in CSS for credit balances, call durations, and phone numbers to keep table columns perfectly aligned.
- **Don't** use standard Bootstrap/Tailwind default grays. Every gray in this app must have a blue/indigo tint to match the palette.
- **Don't** use floating, heavily-shadowed glassmorphism for data tables. Keep the data layer crisp, grounded, and intensely professional. Save the "flashy" effects for the login screen or high-level dashboard charts.
