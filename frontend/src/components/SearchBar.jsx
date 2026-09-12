import { useEffect, useState } from "react";

export default function SearchBar({ onSearch, loading, placeholder }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!value.trim()) {
      setError("");
      return undefined;
    }
    if (value.trim().length < 2) {
      setError("Type at least 2 characters.");
      return undefined;
    }
    setError("");
    const timer = setTimeout(() => onSearch(value.trim()), 300);
    return () => clearTimeout(timer);
  }, [value, onSearch]);

  return (
    <div>
      <div className="flex gap-2">
        <input
          className="w-full rounded border border-gray-300 px-3 py-2"
          placeholder={placeholder || "Search person, phone, vehicle, account, location…"}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-label="Search entities"
        />
        <button
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          type="button"
          onClick={() => {
            setValue("");
            onSearch("");
          }}
        >
          Clear
        </button>
      </div>
      {loading ? <p className="mt-1 text-xs text-gray-500">Searching…</p> : null}
      {error ? <p className="mt-1 text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
