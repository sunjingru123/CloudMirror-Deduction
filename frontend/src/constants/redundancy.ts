import type { MemberRole, RedundancyType } from '@/api/redundancy'

export interface LabeledMeta<T extends string> {
  value: T
  label: string
  color: string
}

/** 冗余模式元数据（顺序即下拉展示顺序）。 */
export const REDUNDANCY_TYPES: LabeledMeta<RedundancyType>[] = [
  { value: 'active_standby', label: '主备模式', color: '#7c3aed' },
  { value: 'manual_standby', label: '手动备用', color: '#a855f7' },
  { value: 'active_active', label: '双活模式', color: '#0d9488' },
]

/** 成员角色元数据。 */
export const MEMBER_ROLES: LabeledMeta<MemberRole>[] = [
  { value: 'primary', label: '主节点', color: '#7c3aed' },
  { value: 'standby', label: '备用节点', color: '#0ea5e9' },
  { value: 'active', label: '双活成员', color: '#0d9488' },
]

/** 冗余关系连线颜色（与普通依赖边区分）。 */
export const REDUNDANCY_EDGE_COLOR = '#8b5cf6'

/** 需要「主节点 + 备用节点」结构的模式。 */
export const STANDBY_REDUNDANCY_TYPES: RedundancyType[] = ['active_standby', 'manual_standby']

const REDUNDANCY_TYPE_MAP = new Map(REDUNDANCY_TYPES.map((item) => [item.value, item]))
const MEMBER_ROLE_MAP = new Map(MEMBER_ROLES.map((item) => [item.value, item]))

export function redundancyTypeMeta(type: RedundancyType): LabeledMeta<RedundancyType> {
  return REDUNDANCY_TYPE_MAP.get(type) ?? { value: type, label: type, color: '#64748b' }
}

export function memberRoleMeta(role: MemberRole): LabeledMeta<MemberRole> {
  return MEMBER_ROLE_MAP.get(role) ?? { value: role, label: role, color: '#64748b' }
}

export function isStandbyTopology(type: RedundancyType): boolean {
  return STANDBY_REDUNDANCY_TYPES.includes(type)
}
