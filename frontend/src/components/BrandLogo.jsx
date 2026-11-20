export default function BrandLogo({ size = 44, className = "" }) {
  return (
    <span
      className={`brand-logo-wrap ${className}`.trim()}
      style={{ "--brand-size": `${size}px` }}
      aria-hidden="true"
    >
      <img
        className="brand-logo"
        src="/icons/icon-128.png"
        alt=""
        width={size}
        height={size}
        decoding="async"
      />
    </span>
  );
}
