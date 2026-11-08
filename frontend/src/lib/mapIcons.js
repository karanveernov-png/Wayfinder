import L from "leaflet";

export const CATEGORY_COLOR = {
  hospital: "#DC2626",
  fuel: "#D97706",
  restaurant: "#059669",
  rest_stop: "#2563EB",
  pharmacy: "#7C3AED",
  lodging: "#0891B2",
};

export const CATEGORY_LETTER = {
  hospital: "H",
  fuel: "F",
  restaurant: "R",
  rest_stop: "S",
  pharmacy: "P",
  lodging: "L",
};

/** Small legend data for the six facility categories, in display order. */
export const FACILITY_LEGEND = [
  { category: "hospital", label: "Hospital", color: CATEGORY_COLOR.hospital, letter: CATEGORY_LETTER.hospital },
  { category: "fuel", label: "Fuel & charging", color: CATEGORY_COLOR.fuel, letter: CATEGORY_LETTER.fuel },
  { category: "restaurant", label: "Restaurant & cafe", color: CATEGORY_COLOR.restaurant, letter: CATEGORY_LETTER.restaurant },
  { category: "rest_stop", label: "Rest stop", color: CATEGORY_COLOR.rest_stop, letter: CATEGORY_LETTER.rest_stop },
  { category: "pharmacy", label: "Pharmacy", color: CATEGORY_COLOR.pharmacy, letter: CATEGORY_LETTER.pharmacy },
  { category: "lodging", label: "Lodging", color: CATEGORY_COLOR.lodging, letter: CATEGORY_LETTER.lodging },
];

/**
 * Facility pin. Verified facilities get a solid filled dot; anything else
 * (address-matched, unverified, unavailable) gets a dashed ring so it is
 * never visually identical to a confirmed location — per API_CONTRACT.md's
 * facility-verification rule of thumb. A `selected` facility (chosen from
 * the map or the list) gets a larger pin with a halo so the two views stay
 * easy to cross-reference.
 *
 * Pins are deliberately oversized relative to the old default so they stay
 * legible when the map is zoomed out to a whole route, and the category
 * letter is drawn in a contrasting color so it reads on both light and
 * dark fills.
 */
export function facilityIcon(category, verified, selected = false) {
  const color = CATEGORY_COLOR[category] || "#475569";
  const letter = CATEGORY_LETTER[category] || "?";
  const border = verified ? `3px solid ${color}` : `2px dashed ${color}`;
  const bg = verified ? color : "#ffffff";
  const textColor = verified ? "#ffffff" : color;
  const size = selected ? 38 : 30;
  const halo = selected
    ? `0 0 0 5px ${color}44, 0 2px 6px rgba(15,23,42,0.5)`
    : "0 2px 5px rgba(15,23,42,0.4)";

  return L.divIcon({
    className: "wm-marker",
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:9999px;
      background:${bg};border:${border};
      display:flex;align-items:center;justify-content:center;
      font:700 ${selected ? 13 : 12}px/1 ui-sans-serif,system-ui,sans-serif;color:${textColor};
      box-shadow:${halo};
    ">${letter}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

const SEVERITY_COLOR = {
  low: "#64748B",
  moderate: "#D97706",
  high: "#DC2626",
  unknown: "#64748B",
};

export function alertIcon(severity) {
  const color = SEVERITY_COLOR[severity] || SEVERITY_COLOR.unknown;
  return L.divIcon({
    className: "wm-marker",
    html: `<div style="
      width:22px;height:22px;transform:rotate(45deg);
      background:${color};border:2px solid #ffffff;
      box-shadow:0 1px 3px rgba(0,0,0,0.4);
    "></div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    popupAnchor: [0, -11],
  });
}

export function fireIcon() {
  return L.divIcon({
    className: "wm-marker",
    html: `<div style="
      width:15px;height:15px;border-radius:9999px;
      background:#DC2626;border:2px solid #ffffff;
      box-shadow:0 0 0 4px #DC262644,0 1px 4px rgba(15,23,42,0.45);
    "></div>`,
    iconSize: [15, 15],
    iconAnchor: [7.5, 7.5],
    popupAnchor: [0, -8],
  });
}

export function endpointIcon(kind) {
  // kind: "origin" | "destination"
  const color = kind === "origin" ? "#16A34A" : "#1E293B";
  const label = kind === "origin" ? "A" : "B";
  return L.divIcon({
    className: "wm-marker",
    html: `<div style="
      width:30px;height:30px;border-radius:9999px 9999px 9999px 0;
      transform:rotate(-45deg);
      background:${color};border:2px solid #ffffff;
      box-shadow:0 1px 4px rgba(0,0,0,0.4);
      display:flex;align-items:center;justify-content:center;
    "><span style="transform:rotate(45deg);color:#fff;font:700 12px/1 ui-sans-serif,system-ui,sans-serif;">${label}</span></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 29],
    popupAnchor: [0, -28],
  });
}
