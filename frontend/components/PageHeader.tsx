export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="naar-eyebrow">{eyebrow}</div>}
        <h1 className="text-3xl font-extrabold text-forest leading-tight">{title}</h1>
        {description && <p className="text-naar-slate mt-2 max-w-2xl leading-relaxed">{description}</p>}
      </div>
      {action}
    </div>
  );
}
