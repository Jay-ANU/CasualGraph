import React from 'react';

type BrandLogoSize = 'sm' | 'md' | 'lg';

interface BrandLogoProps {
  className?: string;
  showText?: boolean;
  size?: BrandLogoSize;
  /** `dark` for dark backgrounds: light wordmark and a hairline ring around the mark. */
  tone?: 'light' | 'dark';
}

const MARK_PX: Record<BrandLogoSize, number> = { sm: 20, md: 24, lg: 32 };
const TEXT_CLASS: Record<BrandLogoSize, string> = {
  sm: 'text-[15px]',
  md: 'text-base',
  lg: 'text-xl',
};

const BrandLogo: React.FC<BrandLogoProps> = ({ className = '', showText = true, size = 'md', tone = 'light' }) => {
  const px = MARK_PX[size];
  const dark = tone === 'dark';
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <img
        src="/brand/logo-mark.svg"
        alt=""
        aria-hidden="true"
        width={px}
        height={px}
        className="shrink-0"
        style={{ width: px, height: px, borderRadius: px / 4, boxShadow: dark ? '0 0 0 1px rgba(255,255,255,0.22), 0 0 18px rgba(139,92,246,0.45)' : undefined }}
      />
      {showText && (
        <span className={`font-semibold tracking-[-0.01em] ${dark ? 'text-white' : 'text-ink'} ${TEXT_CLASS[size]}`}>CausalGraph</span>
      )}
    </span>
  );
};

export default BrandLogo;
