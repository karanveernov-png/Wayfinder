import { useEffect, useState, useCallback } from "react";

function isStandalone() {
  // display-mode: standalone covers installed PWAs on Android/desktop;
  // navigator.standalone is Safari's older, non-standard equivalent for
  // "added to home screen" on iOS, which never fires
  // beforeinstallprompt/display-mode media changes at all.
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

/**
 * Exposes the browser's install prompt as { canInstall, promptInstall(),
 * isInstalled }. canInstall only becomes true on browsers that fire
 * beforeinstallprompt (Chromium-based; not Safari/Firefox, which have no
 * programmatic install prompt at all - those users install via their
 * browser's own "Add to Home Screen" menu item instead, so UI built on
 * this hook should treat canInstall=false as "don't show the button",
 * not as an error.
 */
export function useInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstalled, setIsInstalled] = useState(isStandalone);

  useEffect(() => {
    function onBeforeInstallPrompt(event) {
      event.preventDefault();
      setDeferredPrompt(event);
    }
    function onAppInstalled() {
      setDeferredPrompt(null);
      setIsInstalled(true);
    }
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  const promptInstall = useCallback(async () => {
    if (!deferredPrompt) return null;
    deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    // The prompt can only be used once; discard it either way so
    // canInstall correctly goes back to false until the browser fires
    // beforeinstallprompt again (it won't, until next page load).
    setDeferredPrompt(null);
    return choice.outcome; // "accepted" | "dismissed"
  }, [deferredPrompt]);

  return {
    canInstall: Boolean(deferredPrompt) && !isInstalled,
    isInstalled,
    promptInstall,
  };
}
