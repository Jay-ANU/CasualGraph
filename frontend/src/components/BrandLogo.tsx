import React from 'react';

type BrandLogoSize = 'sm' | 'md' | 'lg' | 'nav';

interface BrandLogoProps {
  className?: string;
  showText?: boolean;
  size?: BrandLogoSize;
}

const sizeClasses: Record<BrandLogoSize, { mark: string; text: string; gap: string }> = {
  sm: {
    mark: 'h-8 w-8',
    text: 'text-[18px]',
    gap: 'gap-2.5',
  },
  md: {
    mark: 'h-9 w-9',
    text: 'text-card-title',
    gap: 'gap-3',
  },
  lg: {
    mark: 'h-10 w-10',
    text: 'text-[24px]',
    gap: 'gap-3.5',
  },
  nav: {
    mark: 'h-8 w-8 lg:h-9 lg:w-9 xl:h-10 xl:w-10',
    text: 'text-card-title lg:text-[22px] xl:text-[24px]',
    gap: 'gap-3 lg:gap-3.5 xl:gap-4',
  },
};

const BrandLogo: React.FC<BrandLogoProps> = ({ className = '', showText = true, size = 'md' }) => {
  const classes = sizeClasses[size];

  return (
    <span className={`inline-flex items-center ${classes.gap} ${className}`}>
      <img
        src="/brand/logo-mark.svg"
        alt=""
        aria-hidden="true"
        className={`${classes.mark} shrink-0`}
        width={40}
        height={40}
      />
      {showText && (
        <span
          className={`font-display font-semibold text-ink ${classes.text}`}
          style={{ letterSpacing: 0 }}
        >
          CausalGraph
        </span>
      )}
    </span>
  );
};

export default BrandLogo;
