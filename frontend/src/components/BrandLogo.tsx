import React from 'react';

type BrandLogoSize = 'sm' | 'md' | 'lg';

interface BrandLogoProps {
  className?: string;
  showText?: boolean;
  size?: BrandLogoSize;
}

const MARK_PX: Record<BrandLogoSize, number> = { sm: 20, md: 24, lg: 32 };
const TEXT_CLASS: Record<BrandLogoSize, string> = {
  sm: 'text-[15px]',
  md: 'text-base',
  lg: 'text-xl',
};

const BrandLogo: React.FC<BrandLogoProps> = ({ className = '', showText = true, size = 'md' }) => {
  const px = MARK_PX[size];
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <img
        src="/brand/logo-mark.svg"
        alt=""
        aria-hidden="true"
        width={px}
        height={px}
        className="shrink-0"
        style={{ width: px, height: px }}
      />
      {showText && (
        <span className={`font-semibold tracking-[-0.01em] text-ink ${TEXT_CLASS[size]}`}>CausalGraph</span>
      )}
    </span>
  );
};

export default BrandLogo;
