import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// The theme lives on the server (config.REEL_THEME) because layout.py has already
// baked it into the SVG by the time the browser sees a frame. Applied before first
// paint where possible, and failing open to "paper" — a missing attribute is the
// original look, so a health check that never answers degrades to what shipped.
fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    if (h?.theme) document.documentElement.setAttribute("data-theme", h.theme);
    // RESTYLE_TO_STORY_REELS.md Step 8 Part 2 — story mode's brand colors,
    // applied as CSS custom properties the same way `theme` becomes
    // data-theme above, so styles.css's story-mode rules stay config-
    // driven rather than hardcoding config.py's own default values.
    const root = document.documentElement.style;
    if (h?.brand_bg) root.setProperty("--brand-bg", h.brand_bg);
    if (h?.brand_accent_1) root.setProperty("--brand-accent-1", h.brand_accent_1);
    if (h?.brand_accent_2) root.setProperty("--brand-accent-2", h.brand_accent_2);
    // Read by StoryStage.tsx's getBrandHandle() — a plain data attribute,
    // not a CSS custom property, since this one is TEXT CONTENT (the
    // watermark/CTA's own copy), not a style value.
    if (h?.brand_handle) document.documentElement.dataset.brandHandle = h.brand_handle;
  })
  .catch(() => {});

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
