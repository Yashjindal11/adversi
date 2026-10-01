export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="#16142B" />
      <path d="M12 14 L29 32 L12 50" fill="none" stroke="#818CF8" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M52 14 L35 32 L52 50" fill="none" stroke="#F59E0B" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="32" cy="32" r="3.5" fill="#2DD4BF" />
    </svg>
  );
}
