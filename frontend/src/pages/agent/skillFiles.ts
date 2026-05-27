export const SKILL_FILE_ACCEPT = '.md,.json,.yaml,.yml,.toml,.zip';

export const SKILL_FILE_ALLOWED_LABEL =
  'SKILL.md, *.skill.md, *.skill.json, *.skill.yaml, *.skill.yml, *.skill.toml, *.skill.zip';

export const SKILL_FILE_MAX_BYTES = 10 * 1024 * 1024;

interface SkillFileLike {
  name: string;
  size: number;
}

export const formatSkillFileSize = (bytes: number): string => {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
};

export const isAllowedSkillFileName = (name: string): boolean => {
  const lowerName = name.trim().toLowerCase();
  return (
    lowerName === 'skill.md' ||
    lowerName.endsWith('.skill.md') ||
    lowerName.endsWith('.skill.json') ||
    lowerName.endsWith('.skill.yaml') ||
    lowerName.endsWith('.skill.yml') ||
    lowerName.endsWith('.skill.toml') ||
    lowerName.endsWith('.skill.zip')
  );
};

export const validateSkillFile = (file: SkillFileLike): { valid: true } | { valid: false; reason: string } => {
  if (!isAllowedSkillFileName(file.name)) {
    return {
      valid: false,
      reason: `Only skill packages are accepted here: ${SKILL_FILE_ALLOWED_LABEL}. Reports belong in Upload.`,
    };
  }

  if (file.size > SKILL_FILE_MAX_BYTES) {
    return {
      valid: false,
      reason: `Skill files must be ${formatSkillFileSize(SKILL_FILE_MAX_BYTES)} or smaller.`,
    };
  }

  return { valid: true };
};
