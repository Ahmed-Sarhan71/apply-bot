"use client";

export function AutoSubmitSelect({ value, options }: { value: string; options: readonly string[] }) {
  return (
    <select
      name="status"
      defaultValue={value}
      onChange={(e) => e.currentTarget.form?.requestSubmit()}
      className="rounded-md border border-black/15 bg-transparent px-2 py-1 text-sm dark:border-white/20"
    >
      {options.map((s) => (
        <option key={s} value={s} className="text-black">
          {s}
        </option>
      ))}
    </select>
  );
}
