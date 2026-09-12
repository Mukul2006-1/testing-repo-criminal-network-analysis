/** Canonical "Name (id)" display used everywhere an entity is shown. */
export default function NameId({ name, id, className, monoClassName }) {
  return (
    <span className={className}>
      <span className="font-extrabold text-ink">{name || id}</span>{" "}
      <span className={`font-mono text-xs font-semibold text-argus-700 ${monoClassName || ""}`}>
        ({id})
      </span>
    </span>
  );
}
