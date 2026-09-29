import { skillLabel } from '@/lib/labels';
import type { Skill } from '@/types/domain';

const ICON_PATH: Record<Skill, JSX.Element> = {
  emergency: (
    <path
      d="M11.5,2 L5,12 L9.5,12 L8.5,18 L15,8 L10.5,8 Z"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinejoin="round"
    />
  ),
  connection: (
    <>
      <rect x={7} y={9} width={6} height={6} rx={1.5} fill="none" stroke="currentColor" strokeWidth={1.6} />
      <line x1={8.5} y1={9} x2={8.5} y2={5} stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" />
      <line x1={11.5} y1={9} x2={11.5} y2={5} stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" />
    </>
  ),
  local_work: (
    <>
      <circle cx={6} cy={14} r={2.6} fill="none" stroke="currentColor" strokeWidth={1.6} />
      <circle cx={14} cy={6} r={2.6} fill="none" stroke="currentColor" strokeWidth={1.6} />
      <line x1={8} y1={12} x2={12} y2={8} stroke="currentColor" strokeWidth={1.6} />
    </>
  )
};

// 1 to 3 skill chips next to the brigade name on the engineer card.
export function SkillIcons({ skills }: { skills: Skill[] }) {
  return (
    <span className="skill-icons">
      {skills.map((skill) => (
        <span key={skill} className="skill-icon" role="img" aria-label={`Навык: ${skillLabel(skill)}`} title={skillLabel(skill)}>
          <svg width={13} height={13} viewBox="0 0 20 20">
            {ICON_PATH[skill]}
          </svg>
        </span>
      ))}
    </span>
  );
}
