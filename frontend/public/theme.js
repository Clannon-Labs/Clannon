// Applies the saved theme before first paint so there is no flash.
// Default (no stored choice): the WORKSPACE (/app) is dark-first — the
// instrument room — while marketing keeps the warm-paper light. Explicit
// choices and "system" always win. Mirrored in src/components/theme.tsx.
(function () {
  try {
    var stored = localStorage.getItem("clannon.theme");
    var dark =
      stored === "dark" ||
      (stored === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches) ||
      (!stored && location.pathname.indexOf("/app") === 0);
    document.documentElement.classList.toggle("dark", dark);
  } catch {
    /* storage unavailable — light via CSS default is fine */
  }
})();
