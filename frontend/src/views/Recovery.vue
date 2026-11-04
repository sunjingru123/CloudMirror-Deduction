<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { topologyApi } from '@/api/topology'
import type { TopologySummary } from '@/api/topology'
import { analysisApi } from '@/api/analysis'
import type { AnalysisResult } from '@/api/analysis'
import { recoveryApi } from '@/api/recovery'
import type { RecoveryRecommendation, RecoveryStrategy, StrategyConfig } from '@/api/recovery'
import { extractErrorMessage } from '@/api/errors'
import {
  SCORING_WEIGHT_LABELS,
  resourceCostMeta,
  riskLevelMeta,
  strategyTypeMeta,
} from '@/constants/recovery'

// --------------------------------------------------------------------------- //
// 状态
// --------------------------------------------------------------------------- //
const topologies = ref<TopologySummary[]>([])
const topologyId = ref<number | null>(null)
const analysis = ref<AnalysisResult | null>(null)
const recommendation = ref<RecoveryRecommendation | null>(null)
const config = ref<StrategyConfig | null>(null)

const loadingTopologies = ref(false)
const loadingContext = ref(false)
const analyzing = ref(false)
const recommending = ref(false)
const loadError = ref('')

// --------------------------------------------------------------------------- //
// 派生数据
// --------------------------------------------------------------------------- //
const hasTopology = computed(() => topologyId.value !== null)
const strategies = computed<RecoveryStrategy[]>(() => recommendation.value?.strategies ?? [])
const recommendedId = computed(() => recommendation.value?.recommended_strategy_id ?? null)

const analysisMetrics = computed(() => {
  if (!analysis.value) return []
  return [
    { label: '故障源', value: String(analysis.value.fault_sources.length), tone: 'danger' },
    { label: '受影响节点', value: String(analysis.value.total_affected_count), tone: 'normal' },
    { label: '直接影响', value: String(analysis.value.direct_affected_count), tone: 'warn' },
    { label: '间接影响', value: String(analysis.value.indirect_affected_count), tone: 'muted' },
    {
      label: '影响比例',
      value: `${(analysis.value.impact_ratio * 100).toFixed(1)}%`,
      tone: 'primary',
    },
  ]
})

const hasFaultSources = computed(() => (analysis.value?.fault_sources.length ?? 0) > 0)

const maxRecoveryTime = computed(() =>
  Math.max(1, ...strategies.value.map((item) => item.estimated_recovery_time)),
)
const maxScore = computed(() =>
  Math.max(1, ...strategies.value.map((item) => item.recommendation_score)),
)

// --------------------------------------------------------------------------- //
// 工具函数
// --------------------------------------------------------------------------- //
function isRecommended(strategy: RecoveryStrategy): boolean {
  return recommendedId.value !== null && strategy.strategy_id === recommendedId.value
}

function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} 秒`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds - minutes * 60)
  return rest === 0 ? `${minutes} 分` : `${minutes} 分 ${rest} 秒`
}

function barWidth(value: number, maximum: number): string {
  return `${Math.max(4, Math.round((value / maximum) * 100))}%`
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (input: number) => String(input).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

// --------------------------------------------------------------------------- //
// 加载
// --------------------------------------------------------------------------- //
async function loadTopologies() {
  loadingTopologies.value = true
  loadError.value = ''
  try {
    const { data } = await topologyApi.list()
    topologies.value = data
    if (topologyId.value === null && data.length > 0) {
      topologyId.value = data[0].id
      await loadContext()
    }
  } catch (error) {
    loadError.value = extractErrorMessage(error, '加载拓扑列表失败')
  } finally {
    loadingTopologies.value = false
  }
}

async function loadLatestAnalysis() {
  if (topologyId.value === null) {
    analysis.value = null
    return
  }
  try {
    const { data } = await analysisApi.latest(topologyId.value)
    analysis.value = data
  } catch {
    // 尚无分析记录（404）时视为没有分析结果
    analysis.value = null
  }
}

async function loadConfig() {
  if (topologyId.value === null) {
    config.value = null
    return
  }
  try {
    const { data } = await recoveryApi.strategies(topologyId.value)
    config.value = data
  } catch {
    config.value = null
  }
}

async function loadContext() {
  recommendation.value = null
  loadingContext.value = true
  try {
    await Promise.all([loadLatestAnalysis(), loadConfig()])
  } finally {
    loadingContext.value = false
  }
}

function onTopologyChange() {
  void loadContext()
}

function reloadAll() {
  void loadContext()
}

// --------------------------------------------------------------------------- //
// 操作
// --------------------------------------------------------------------------- //
async function runAnalysis() {
  if (topologyId.value === null) {
    ElMessage.warning('请先选择拓扑')
    return
  }
  analyzing.value = true
  try {
    const { data } = await analysisApi.analyze(topologyId.value)
    analysis.value = data
    recommendation.value = null
    if (data.fault_sources.length === 0) {
      ElMessage.info('分析完成：当前没有激活故障，无法生成恢复策略')
    } else {
      ElMessage.success('分析完成，可生成恢复策略对比')
    }
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '传播分析失败'))
  } finally {
    analyzing.value = false
  }
}

async function generateRecommendation() {
  if (topologyId.value === null) {
    ElMessage.warning('请先选择拓扑')
    return
  }
  recommending.value = true
  try {
    const { data } = await recoveryApi.recommend(
      topologyId.value,
      analysis.value?.analysis_id ?? null,
    )
    recommendation.value = data
    ElMessage.success('已生成恢复策略对比')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '生成恢复策略失败'))
  } finally {
    recommending.value = false
  }
}

onMounted(loadTopologies)
</script>

<template>
  <div class="rc">
    <header class="cm-page-header">
      <h1 class="cm-page-title">恢复策略</h1>
      <p class="cm-page-subtitle">
        基于最近一次故障传播分析结果，按规则对比三类恢复策略的估算指标并给出推荐。
        策略评分是可解释的加权规则，恢复时间与成本均为模拟估算值，不是生产环境测量值。
      </p>
    </header>

    <div class="rc-toolbar">
      <div class="rc-toolbar-item">
        <span class="rc-toolbar-label">目标拓扑</span>
        <el-select
          v-model="topologyId"
          class="rc-select"
          placeholder="请选择拓扑"
          :loading="loadingTopologies"
          @change="onTopologyChange"
        >
          <el-option
            v-for="item in topologies"
            :key="item.id"
            :label="`${item.name}（${item.node_count} 节点 / ${item.edge_count} 依赖）`"
            :value="item.id"
          />
        </el-select>
      </div>
      <div class="rc-toolbar-actions">
        <el-button :loading="loadingContext || loadingTopologies" @click="reloadAll">
          刷新
        </el-button>
        <el-button :loading="analyzing" :disabled="!hasTopology" @click="runAnalysis">
          运行传播分析
        </el-button>
        <el-button
          type="primary"
          :loading="recommending"
          :disabled="!hasTopology || !hasFaultSources"
          @click="generateRecommendation"
        >
          生成策略对比
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
      class="rc-alert"
    >
      <template #default>
        <span>请确认后端服务已启动，然后点击「刷新」重试。</span>
      </template>
    </el-alert>

    <el-empty v-if="!loadingTopologies && topologies.length === 0" description="暂无拓扑">
      <template #description>
        <p class="rc-empty-title">暂无拓扑</p>
        <p class="rc-empty-sub">请先前往「系统拓扑」页面创建拓扑与依赖关系。</p>
      </template>
    </el-empty>

    <template v-else>
      <!-- 分析上下文 -->
      <section v-if="analysis" class="rc-context">
        <div class="rc-context-head">
          <span class="rc-context-id">分析 #{{ analysis.analysis_id }}</span>
          <span class="rc-context-time">{{ formatTime(analysis.analysis_time) }}</span>
        </div>
        <div class="rc-metrics">
          <div v-for="item in analysisMetrics" :key="item.label" class="rc-metric">
            <span class="rc-metric-value" :class="`is-${item.tone}`">{{ item.value }}</span>
            <span class="rc-metric-label">{{ item.label }}</span>
          </div>
        </div>
        <p v-if="!hasFaultSources" class="rc-context-warning">
          该分析没有激活故障源，无法生成恢复策略。请先前往「故障模拟」注入故障后重新分析。
        </p>
      </section>

      <section v-else-if="!loadingContext" class="rc-context is-empty">
        <p class="rc-context-empty">
          该拓扑尚无传播分析结果。请先点击「运行传播分析」，或前往「故障模拟」注入故障后再分析。
        </p>
      </section>

      <!-- 推荐结论 -->
      <section
        v-if="recommendation"
        class="rc-recommend"
        :class="{ 'is-none': recommendation.recommended_strategy_id === null }"
      >
        <div class="rc-recommend-label">推荐结论</div>
        <p class="rc-recommend-text">{{ recommendation.recommendation_reason }}</p>
        <p class="rc-recommend-notice">{{ recommendation.estimation_notice }}</p>
      </section>

      <!-- 策略对比 -->
      <section v-if="strategies.length > 0" class="rc-compare">
        <div class="rc-compare-grid">
          <!-- 表头 -->
          <div class="rc-corner">指标</div>
          <div
            v-for="strategy in strategies"
            :key="`head-${strategy.strategy_id}`"
            class="rc-head"
            :class="{
              'is-recommended': isRecommended(strategy),
              'is-inapplicable': !strategy.applicable,
            }"
          >
            <span
              class="rc-head-dot"
              :style="{ background: strategyTypeMeta(strategy.strategy_type).color }"
            ></span>
            <div class="rc-head-body">
              <span class="rc-head-name">{{ strategy.strategy_name }}</span>
              <span class="rc-head-tags">
                <span class="rc-badge" :class="strategy.applicable ? 'is-ok' : 'is-off'">
                  {{ strategy.applicable ? '适用' : '不适用' }}
                </span>
                <span v-if="isRecommended(strategy)" class="rc-badge is-rec">推荐</span>
              </span>
            </div>
          </div>

          <!-- 预计恢复时间 -->
          <div class="rc-row-label">预计恢复时间</div>
          <div
            v-for="strategy in strategies"
            :key="`time-${strategy.strategy_id}`"
            class="rc-cell"
            :class="{ 'is-inapplicable': !strategy.applicable }"
          >
            <span class="rc-cell-value">{{ formatSeconds(strategy.estimated_recovery_time) }}</span>
            <span class="rc-bar">
              <span
                class="rc-bar-fill is-time"
                :style="{ width: barWidth(strategy.estimated_recovery_time, maxRecoveryTime) }"
              ></span>
            </span>
          </div>

          <!-- 估算影响节点 -->
          <div class="rc-row-label">估算影响节点</div>
          <div
            v-for="strategy in strategies"
            :key="`nodes-${strategy.strategy_id}`"
            class="rc-cell"
            :class="{ 'is-inapplicable': !strategy.applicable }"
          >
            <span class="rc-cell-value">{{ strategy.estimated_affected_nodes }} 个</span>
            <span class="rc-cell-hint">需停机或短暂失去服务</span>
          </div>

          <!-- 资源成本 -->
          <div class="rc-row-label">资源成本</div>
          <div
            v-for="strategy in strategies"
            :key="`cost-${strategy.strategy_id}`"
            class="rc-cell"
            :class="{ 'is-inapplicable': !strategy.applicable }"
          >
            <span
              class="rc-dot"
              :style="{ background: resourceCostMeta(strategy.estimated_resource_cost).color }"
            ></span>
            <span class="rc-cell-value">{{
              resourceCostMeta(strategy.estimated_resource_cost).label
            }}</span>
          </div>

          <!-- 风险等级 -->
          <div class="rc-row-label">操作风险</div>
          <div
            v-for="strategy in strategies"
            :key="`risk-${strategy.strategy_id}`"
            class="rc-cell"
            :class="{ 'is-inapplicable': !strategy.applicable }"
          >
            <span
              class="rc-dot"
              :style="{ background: riskLevelMeta(strategy.risk_level).color }"
            ></span>
            <span class="rc-cell-value">{{ riskLevelMeta(strategy.risk_level).label }}</span>
          </div>

          <!-- 综合评分 -->
          <div class="rc-row-label">综合评分</div>
          <div
            v-for="strategy in strategies"
            :key="`score-${strategy.strategy_id}`"
            class="rc-cell"
            :class="{ 'is-inapplicable': !strategy.applicable }"
          >
            <span class="rc-cell-value is-score">{{ strategy.recommendation_score.toFixed(2) }}</span>
            <span class="rc-bar">
              <span
                class="rc-bar-fill is-score"
                :style="{ width: barWidth(strategy.recommendation_score, maxScore) }"
              ></span>
            </span>
          </div>

          <!-- 不适用原因 -->
          <template v-if="strategies.some((item) => !item.applicable)">
            <div class="rc-row-label">不适用原因</div>
            <div
              v-for="strategy in strategies"
              :key="`reason-${strategy.strategy_id}`"
              class="rc-cell rc-cell-reason"
              :class="{ 'is-inapplicable': !strategy.applicable }"
            >
              <template v-if="!strategy.applicable">
                {{ strategy.inapplicable_reason }}
              </template>
              <span v-else class="rc-muted">—</span>
            </div>
          </template>
        </div>
      </section>

      <!-- 策略明细 -->
      <section v-if="strategies.length > 0" class="rc-details">
        <article
          v-for="strategy in strategies"
          :key="`detail-${strategy.strategy_id}`"
          class="rc-detail"
          :class="{ 'is-inapplicable': !strategy.applicable }"
        >
          <header class="rc-detail-head">
            <span
              class="rc-detail-dot"
              :style="{ background: strategyTypeMeta(strategy.strategy_type).color }"
            ></span>
            <h3 class="rc-detail-title">{{ strategy.strategy_name }}</h3>
            <span class="rc-detail-type">{{ strategyTypeMeta(strategy.strategy_type).label }}</span>
          </header>
          <p class="rc-detail-desc">{{ strategy.description }}</p>
          <p v-if="!strategy.applicable" class="rc-detail-warning">
            不适用：{{ strategy.inapplicable_reason }}
          </p>

          <div
            v-if="strategy.strategy_type === 'failover' && strategy.prerequisite_checks.length > 0"
            class="rc-redundancy"
          >
            <div class="rc-redundancy-head">
              <span class="rc-redundancy-label">显式冗余判定</span>
              <span v-if="strategy.redundancy_group_name" class="rc-redundancy-group">
                冗余组「{{ strategy.redundancy_group_name }}」#{{ strategy.redundancy_group_id }}
              </span>
              <span v-else class="rc-redundancy-group is-muted">未关联显式冗余组</span>
            </div>

            <p v-if="strategy.selection_reason" class="rc-redundancy-reason">
              {{ strategy.selection_reason }}
            </p>

            <div v-if="strategy.standby_candidates.length > 0" class="rc-sub">
              <span class="rc-sub-label">备用节点候选（按 priority 升序，数值越小越优先）</span>
              <ul class="rc-candidates">
                <li
                  v-for="candidate in strategy.standby_candidates"
                  :key="`candidate-${candidate.node_id}`"
                  class="rc-candidate"
                  :class="{ 'is-eligible': candidate.eligible }"
                >
                  <span
                    class="rc-candidate-dot"
                    :style="{ background: candidate.eligible ? '#16a34a' : '#dc2626' }"
                  ></span>
                  <span class="rc-candidate-name">{{ candidate.node_name }}</span>
                  <span v-if="candidate.priority !== null" class="rc-candidate-priority">
                    P{{ candidate.priority }}
                  </span>
                  <span class="rc-candidate-detail">{{ candidate.detail }}</span>
                </li>
              </ul>
            </div>

            <div class="rc-sub">
              <span class="rc-sub-label">前置条件检查</span>
              <ul class="rc-checks">
                <li
                  v-for="(check, index) in strategy.prerequisite_checks"
                  :key="`check-${index}`"
                  class="rc-check"
                >
                  <span class="rc-check-flag" :class="check.passed ? 'is-ok' : 'is-fail'">
                    {{ check.passed ? '✓' : '✕' }}
                  </span>
                  <span class="rc-check-name">{{ check.check_name }}</span>
                  <span class="rc-check-detail">{{ check.detail }}</span>
                </li>
              </ul>
            </div>
          </div>
          <div class="rc-detail-columns">
            <div class="rc-detail-col">
              <h4>优势</h4>
              <ul>
                <li v-for="(item, index) in strategy.advantages" :key="`adv-${index}`">
                  {{ item }}
                </li>
              </ul>
            </div>
            <div class="rc-detail-col">
              <h4>劣势</h4>
              <ul>
                <li v-for="(item, index) in strategy.disadvantages" :key="`dis-${index}`">
                  {{ item }}
                </li>
              </ul>
            </div>
            <div class="rc-detail-col">
              <h4>前置条件</h4>
              <ul>
                <li v-for="(item, index) in strategy.prerequisites" :key="`pre-${index}`">
                  {{ item }}
                </li>
              </ul>
            </div>
          </div>
        </article>
      </section>

      <p v-if="!recommendation && hasFaultSources" class="rc-cta">
        已读取分析结果，点击右上角「生成策略对比」调用后端恢复策略推荐接口。
      </p>

      <!-- 评分规则 -->
      <section v-if="config" class="rc-rules">
        <h2 class="rc-rules-title">评分规则</h2>
        <p class="rc-rules-desc">
          各分项归一化后按固定权重加权（合计 100%），乘以 100 得到综合评分；
          恢复时间以 {{ config.reference_recovery_seconds }} 秒为归一化参考值。
          不适用策略仍会计算评分，但永远不会被选为推荐策略。
        </p>
        <ul class="rc-weights">
          <li v-for="item in SCORING_WEIGHT_LABELS" :key="item.key" class="rc-weight">
            <span class="rc-weight-label">{{ item.label }}</span>
            <span class="rc-weight-value">
              {{ Math.round(config.scoring_weights[item.key] * 100) }}%
            </span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.rc {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 工具条 */
.rc-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 0;
  border-top: 1px solid var(--cm-border);
  border-bottom: 1px solid var(--cm-border);
}

.rc-toolbar-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rc-toolbar-label {
  font-size: 13px;
  color: var(--cm-text-muted);
}

.rc-select {
  width: 320px;
}

.rc-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.rc-alert {
  margin-top: -8px;
}

/* 空状态 */
.rc-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cm-text);
}

.rc-empty-sub {
  margin-top: 8px;
  font-size: 13px;
  color: var(--cm-text-muted);
}

/* 分析上下文 */
.rc-context {
  padding: 18px 0 20px;
  border-bottom: 1px solid var(--cm-border);
}

.rc-context.is-empty {
  border-bottom-style: dashed;
}

.rc-context-head {
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.rc-context-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--cm-primary);
}

.rc-context-time {
  font-size: 12.5px;
  color: var(--cm-text-muted);
}

.rc-metrics {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 16px;
}

.rc-metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rc-metric-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.rc-metric-value.is-danger {
  color: #dc2626;
}

.rc-metric-value.is-warn {
  color: #f97316;
}

.rc-metric-value.is-muted {
  color: #eab308;
}

.rc-metric-value.is-primary {
  color: var(--cm-primary);
}

.rc-metric-label {
  font-size: 12px;
  color: var(--cm-text-muted);
}

.rc-context-warning,
.rc-context-empty {
  margin-top: 14px;
  font-size: 13px;
  color: var(--cm-text-secondary);
  line-height: 1.7;
}

.rc-context-warning {
  padding-left: 12px;
  border-left: 3px solid #f59e0b;
}

/* 推荐结论 */
.rc-recommend {
  padding: 20px 22px;
  border-radius: var(--cm-radius);
  background: linear-gradient(120deg, rgba(31, 111, 235, 0.1), rgba(6, 182, 212, 0.08));
  border-left: 3px solid var(--cm-primary);
}

.rc-recommend.is-none {
  background: rgba(220, 38, 38, 0.05);
  border-left-color: #dc2626;
}

.rc-recommend-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 1.2px;
  color: var(--cm-primary);
  text-transform: uppercase;
}

.rc-recommend.is-none .rc-recommend-label {
  color: #dc2626;
}

.rc-recommend-text {
  margin-top: 10px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.75;
}

.rc-recommend-notice {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--cm-text-secondary);
  line-height: 1.6;
}

/* 对比矩阵 */
.rc-compare-grid {
  display: grid;
  grid-template-columns: 132px repeat(3, minmax(0, 1fr));
  align-items: stretch;
  border-top: 1px solid var(--cm-border);
}

.rc-corner,
.rc-head {
  padding: 16px 14px;
  border-bottom: 1px solid var(--cm-border);
}

.rc-corner {
  font-size: 12px;
  font-weight: 600;
  color: var(--cm-text-muted);
  display: flex;
  align-items: flex-end;
}

.rc-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border-left: 1px solid var(--cm-border);
  transition: background-color 0.2s ease;
}

.rc-head.is-recommended {
  background: rgba(31, 111, 235, 0.06);
  box-shadow: inset 0 2px 0 var(--cm-primary);
}

.rc-head.is-inapplicable {
  background: rgba(15, 23, 42, 0.02);
}

.rc-head-dot {
  margin-top: 5px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.rc-head-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rc-head-name {
  font-size: 15px;
  font-weight: 700;
}

.rc-head-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rc-badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.6;
}

.rc-badge.is-ok {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.12);
}

.rc-badge.is-off {
  color: #b45309;
  background: rgba(245, 158, 11, 0.16);
}

.rc-badge.is-rec {
  color: #1d4ed8;
  background: rgba(31, 111, 235, 0.16);
}

.rc-row-label {
  padding: 14px;
  font-size: 13px;
  color: var(--cm-text-secondary);
  border-bottom: 1px solid var(--cm-border);
  display: flex;
  align-items: center;
}

.rc-cell {
  padding: 14px;
  border-left: 1px solid var(--cm-border);
  border-bottom: 1px solid var(--cm-border);
  display: flex;
  flex-direction: column;
  gap: 6px;
  justify-content: center;
}

.rc-cell.is-inapplicable {
  opacity: 0.62;
}

.rc-cell-value {
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.rc-cell-value.is-score {
  font-size: 18px;
  color: var(--cm-primary);
}

.rc-cell-hint {
  font-size: 11.5px;
  color: var(--cm-text-muted);
}

.rc-cell-reason {
  font-size: 12.5px;
  line-height: 1.65;
  color: #b45309;
}

.rc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.rc-muted {
  color: var(--cm-text-muted);
}

.rc-bar {
  height: 4px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.07);
  overflow: hidden;
}

.rc-bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.35s ease;
}

.rc-bar-fill.is-time {
  background: linear-gradient(90deg, #0ea5e9, #06b6d4);
}

.rc-bar-fill.is-score {
  background: linear-gradient(90deg, #1f6feb, #6366f1);
}

/* 策略明细 */
.rc-details {
  display: flex;
  flex-direction: column;
}

.rc-detail {
  padding: 22px 0;
  border-bottom: 1px solid var(--cm-border);
}

.rc-detail.is-inapplicable {
  opacity: 0.78;
}

.rc-detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rc-detail-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.rc-detail-title {
  font-size: 16px;
  font-weight: 700;
}

.rc-detail-type {
  font-size: 12px;
  color: var(--cm-text-muted);
}

.rc-detail-desc {
  margin-top: 10px;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--cm-text-secondary);
}

.rc-detail-warning {
  margin-top: 10px;
  padding-left: 12px;
  border-left: 3px solid #f59e0b;
  font-size: 13px;
  color: #b45309;
  line-height: 1.7;
}

.rc-redundancy {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px dashed #c4b5fd;
  background: #faf8ff;
}

.rc-redundancy-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
}

.rc-redundancy-label {
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
  color: #7c3aed;
}

.rc-redundancy-group {
  font-size: 12.5px;
  color: var(--cm-text-secondary);
}

.rc-redundancy-group.is-muted {
  color: var(--cm-text-muted);
}

.rc-redundancy-reason {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--cm-text-secondary);
}

.rc-sub {
  margin-top: 12px;
}

.rc-sub-label {
  display: block;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
  color: var(--cm-text-muted);
}

.rc-candidates,
.rc-checks {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rc-candidate,
.rc-check {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid var(--cm-border);
  font-size: 12.5px;
}

.rc-candidate.is-eligible {
  border-color: #86efac;
}

.rc-candidate-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}

.rc-candidate-name,
.rc-check-name {
  font-weight: 600;
  color: var(--cm-text);
}

.rc-candidate-priority {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--cm-primary-soft);
  font-size: 11px;
  font-weight: 700;
  color: var(--cm-primary);
}

.rc-candidate-detail,
.rc-check-detail {
  color: var(--cm-text-secondary);
  flex: 1 1 240px;
}

.rc-check-flag {
  font-weight: 700;
}

.rc-check-flag.is-ok {
  color: #16a34a;
}

.rc-check-flag.is-fail {
  color: #dc2626;
}

.rc-detail-columns {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 18px 28px;
}

.rc-detail-col h4 {
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--cm-text-muted);
}

.rc-detail-col ul {
  margin: 10px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rc-detail-col li {
  font-size: 13px;
  line-height: 1.7;
  color: var(--cm-text-secondary);
}

/* 提示与规则 */
.rc-cta {
  font-size: 13px;
  color: var(--cm-text-secondary);
}

.rc-rules {
  padding-top: 4px;
}

.rc-rules-title {
  font-size: 15px;
  font-weight: 700;
}

.rc-rules-desc {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--cm-text-secondary);
  max-width: 820px;
}

.rc-weights {
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
}

.rc-weight {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.rc-weight-label {
  font-size: 12.5px;
  color: var(--cm-text-muted);
}

.rc-weight-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--cm-text);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 860px) {
  .rc-select {
    width: 100%;
  }

  .rc-compare-grid {
    grid-template-columns: 100px repeat(3, minmax(120px, 1fr));
    overflow-x: auto;
  }
}
</style>
