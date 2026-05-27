import { isAllowedSkillFileName, validateSkillFile } from './skillFiles';

describe('skill file validation', () => {
  it('accepts explicit skill manifests and packaged skill archives', () => {
    expect(isAllowedSkillFileName('SKILL.md')).toBe(true);
    expect(isAllowedSkillFileName('esg-research.skill.md')).toBe(true);
    expect(isAllowedSkillFileName('evidence.skill.json')).toBe(true);
    expect(isAllowedSkillFileName('planner.skill.yaml')).toBe(true);
    expect(isAllowedSkillFileName('bundle.skill.zip')).toBe(true);
  });

  it('rejects ordinary reports and generic archives', () => {
    expect(isAllowedSkillFileName('apple-report.pdf')).toBe(false);
    expect(isAllowedSkillFileName('notes.txt')).toBe(false);
    expect(isAllowedSkillFileName('skill.zip')).toBe(false);
    expect(validateSkillFile({ name: 'annual-report.pdf', size: 42 })).toEqual({
      valid: false,
      reason: expect.stringContaining('Reports belong in Upload'),
    });
  });
});
