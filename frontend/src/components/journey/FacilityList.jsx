import { useEffect, useRef } from "react";
import { Fuel, Coffee, Hospital, ParkingCircle, Pill, Hotel, MapPin } from "lucide-react";
import { FACILITY_CATEGORY_LABELS, facilityVerificationLabel, formatDistance, isFacilityVerified } from "../../lib/format.js";
import { CATEGORY_COLOR } from "../../lib/mapIcons.js";

const CATEGORY_ICON = {
  hospital: Hospital,
  fuel: Fuel,
  restaurant: Coffee,
  rest_stop: ParkingCircle,
  pharmacy: Pill,
  lodging: Hotel,
};

export default function FacilityList({
  facilities,
  emptyLabel = "No facilities found.",
  selectedId = null,
  onSelect,
}) {
  if (!facilities || facilities.length === 0) {
    return <p className="text-sm text-slate-500">{emptyLabel}</p>;
  }

  return (
    <ul className="space-y-3">
      {facilities.map((facility, idx) => {
        const Icon = CATEGORY_ICON[facility.category] || MapPin;
        const verified = isFacilityVerified(facility);
        const facilityId = facility.id || `facility-${idx}`;
        const selected = selectedId != null && facilityId === selectedId;
        return (
          <FacilityRow
            key={facilityId}
            facility={facility}
            Icon={Icon}
            verified={verified}
            selected={selected}
            onClick={onSelect ? () => onSelect(facilityId) : undefined}
          />
        );
      })}
    </ul>
  );
}

function FacilityRow({ facility, Icon, verified, selected, onClick }) {
  const ref = useRef(null);

  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);

  const Tag = onClick ? "button" : "div";
  const color = CATEGORY_COLOR[facility.category] || "#475569";

  return (
    <li>
      <Tag
        ref={ref}
        type={onClick ? "button" : undefined}
        onClick={onClick}
        className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-all duration-150 ${
          selected
            ? "border-[#203C5A] bg-[#EAF0F6]"
            : "border-slate-100 hover:-translate-y-0.5 hover:border-slate-200 hover:bg-slate-50 hover:shadow-sm"
        } ${onClick ? "cursor-pointer" : ""}`}
      >
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
          style={{ backgroundColor: `${color}1A`, color }}
        >
          <Icon size={18} />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{facility.name || "Unnamed facility"}</p>
          <p className="text-xs text-slate-500">
            {FACILITY_CATEGORY_LABELS[facility.category] || facility.category}
            {facility.distance_km !== null && facility.distance_km !== undefined && (
              <> · {formatDistance(facility.distance_km)}</>
            )}
          </p>
          <p className={`mt-0.5 text-xs ${verified ? "text-emerald-700" : "text-amber-700"}`}>
            {facilityVerificationLabel(facility.verification_status)}
          </p>
          {facility.address && <p className="mt-0.5 truncate text-xs text-slate-400">{facility.address}</p>}
        </div>
      </Tag>
    </li>
  );
}
