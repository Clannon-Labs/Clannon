/**
 * Copy text from secure production origins and plain-HTTP LAN development.
 * Clipboard.writeText is unavailable on insecure non-localhost origins, so the
 * hidden-textarea path is a required fallback, not legacy decoration.
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Permission or insecure-context refusal: use the DOM fallback below.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.readOnly = true;
  textarea.setAttribute("aria-hidden", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Copy was not available.");
}
