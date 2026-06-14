// Applies the saved theme before first paint so there is no flash.
// Default (no stored choice) is LIGHT — the warm-paper brand, most readable.
// Dark is opt-in via the toggle, or "system" to follow the OS.
(function () {
  try {
    var stored = localStorage.getItem("clannon.theme");
    var dark =
      stored === "dark" ||
      (stored === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch {
    /* storage unavailable — light via CSS default is fine */
  }
})();
