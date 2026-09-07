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
  })
  .catch(() => {});

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
