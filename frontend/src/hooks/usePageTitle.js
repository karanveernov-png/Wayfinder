import { useEffect } from "react";

/**
 * Sets the document title for the current route. Restores the previous title
 * on unmount. Lightweight, no external deps.
 */
export function usePageTitle(title) {
  const baseTitle = "Waymark";

  useEffect(() => {
    const fullTitle = title ? `${title} — ${baseTitle}` : baseTitle;
    const prevTitle = document.title;
    document.title = fullTitle;
    return () => {
      document.title = prevTitle;
    };
  }, [title]);
}