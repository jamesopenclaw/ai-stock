<template>
  <div class="system-settings-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>系统设置</span>
            <span class="header-desc">用供应商预设管理模型接入，减少手动填写 Base URL 和模型名。</span>
          </div>
          <el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="10" animated />
      <template v-else>
        <div class="settings-overview">
          <div class="overview-card">
            <span class="overview-label">LLM 辅助</span>
            <strong class="overview-value">{{ configForm.llmEnabled ? '已启用' : '未启用' }}</strong>
            <span class="overview-tip">只用于解释增强，不参与交易裁决。</span>
          </div>
          <div class="overview-card">
            <span class="overview-label">当前供应商</span>
            <strong class="overview-value">{{ selectedProvider.label }}</strong>
            <span class="overview-tip">{{ selectedProvider.summary }}</span>
          </div>
          <div class="overview-card">
            <span class="overview-label">密钥状态</span>
            <strong class="overview-value">{{ configForm.llmHasApiKey ? '已保存' : '未保存' }}</strong>
            <span class="overview-tip">留空保存不会覆盖已有密钥。</span>
          </div>
        </div>

        <el-row :gutter="20">
          <el-col :span="14">
            <el-card class="section-card">
              <template #header>
                <span>模型接入</span>
              </template>

              <el-form label-width="110px">
                <el-form-item label="启用辅助">
                  <div class="form-block">
                    <el-switch v-model="configForm.llmEnabled" />
                    <div class="form-hint">启用后，三池页和卖点页会增加人话解释和摘要。</div>
                  </div>
                </el-form-item>

                <el-form-item label="供应商">
                  <div class="form-block">
                    <el-select
                      v-model="configForm.llmProvider"
                      style="width: 100%"
                      @change="handleProviderChange"
                    >
                      <el-option
                        v-for="provider in providerOptions"
                        :key="provider.value"
                        :label="provider.label"
                        :value="provider.value"
                      />
                    </el-select>
                    <div class="provider-summary">
                      <el-tag size="small" type="info">{{ selectedProvider.label }}</el-tag>
                      <span>{{ selectedProvider.summary }}</span>
                    </div>
                  </div>
                </el-form-item>

                <el-form-item label="模型名称">
                  <div class="form-block">
                    <el-select
                      v-if="providerModels.length"
                      v-model="configForm.llmModel"
                      style="width: 100%"
                      filterable
                      allow-create
                      default-first-option
                      placeholder="请选择模型"
                    >
                      <el-option
                        v-for="model in providerModels"
                        :key="model"
                        :label="model"
                        :value="model"
                      />
                    </el-select>
                    <el-input
                      v-else
                      v-model="configForm.llmModel"
                      :placeholder="isVolcengineProvider ? '请输入火山方舟 Endpoint ID' : '请输入模型名'"
                    />
                    <div class="form-hint">
                      {{
                        providerModels.length
                          ? '可直接下拉选择，也可临时输入兼容模型名。'
                          : isVolcengineProvider
                            ? '火山引擎通常填写你在方舟里创建的推理接入点 Endpoint ID。'
                            : '自定义供应商请手动填写模型名。'
                      }}
                    </div>
                  </div>
                </el-form-item>

                <el-form-item label="Base URL">
                  <div class="form-block">
                    <el-input
                      v-model="configForm.llmBaseUrl"
                      :disabled="!isCustomProvider"
                      :placeholder="isCustomProvider ? '请输入兼容接口地址' : '供应商预设会自动填写'"
                    />
                    <div class="form-hint">
                      {{ isCustomProvider ? '自定义模式下需手动填写兼容接口地址。' : '当前为供应商预设地址，切换供应商会自动更新。' }}
                    </div>
                  </div>
                </el-form-item>

                <el-form-item label="API Key">
                  <div class="form-block">
                    <el-input
                      v-model="configForm.llmApiKey"
                      type="password"
                      show-password
                      placeholder="留空则保持不变"
                    />
                    <div class="config-inline-row">
                      <el-tag
                        v-if="configForm.llmHasApiKey && !configForm.clearLlmApiKey"
                        size="small"
                        type="success"
                      >
                        数据库已保存密钥
                      </el-tag>
                      <el-checkbox v-model="configForm.clearLlmApiKey">保存时清空已存密钥</el-checkbox>
                    </div>
                  </div>
                </el-form-item>
              </el-form>
            </el-card>
          </el-col>

          <el-col :span="10">
            <el-card class="section-card">
              <template #header>
                <span>运行参数</span>
              </template>
              <el-form label-width="100px">
                <el-form-item label="超时秒数">
                  <el-input-number
                    v-model="configForm.llmTimeoutSeconds"
                    :min="1"
                    :max="60"
                    :precision="1"
                    :step="1"
                    style="width: 100%"
                  />
                </el-form-item>

                <el-form-item label="温度">
                  <div class="form-block">
                    <el-slider v-model="configForm.llmTemperature" :min="0" :max="1.5" :step="0.1" show-input />
                    <div class="form-hint">解释型任务建议保持低温度，减少文案飘移。</div>
                  </div>
                </el-form-item>

                <el-form-item label="输入条数">
                  <div class="form-block">
                    <el-input-number
                      v-model="configForm.llmMaxInputItems"
                      :min="1"
                      :max="20"
                      :step="1"
                      style="width: 100%"
                    />
                    <div class="form-hint">限制单次送入模型的股票数量，控制成本和延迟。</div>
                  </div>
                </el-form-item>
              </el-form>
            </el-card>

            <el-card class="section-card">
              <template #header>
                <span>预设说明</span>
              </template>
              <div class="note-list">
                <div class="note-item">当前页是 OpenAI 兼容接口预设，不直接改变交易规则。</div>
                <div class="note-item">主流供应商可直接下拉切换；特殊平台请使用“自定义”。</div>
                <div class="note-item">模型配置保存到数据库，优先级高于 `.env` 默认值。</div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '../api'

const providerOptions = [
  {
    value: 'openai',
    label: 'OpenAI',
    summary: '官方 OpenAI 接口预设',
    baseUrl: 'https://api.openai.com/v1',
    models: ['gpt-5-mini', 'gpt-5', 'gpt-4.1-mini']
  },
  {
    value: 'gemini',
    label: 'Google Gemini',
    summary: 'Gemini OpenAI 兼容接口预设',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    models: ['gemini-2.5-flash', 'gemini-2.5-pro']
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    summary: 'DeepSeek 官方兼容接口预设',
    baseUrl: 'https://api.deepseek.com',
    models: ['deepseek-chat', 'deepseek-reasoner']
  },
  {
    value: 'moonshot',
    label: 'Moonshot',
    summary: 'Kimi / Moonshot 官方接口预设',
    baseUrl: 'https://api.moonshot.cn/v1',
    models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k']
  },
  {
    value: 'qwen',
    label: '通义千问',
    summary: '阿里云百炼兼容模式预设',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: ['qwen-turbo', 'qwen-plus', 'qwen-max']
  },
  {
    value: 'siliconflow',
    label: 'SiliconFlow',
    summary: 'SiliconFlow 聚合平台兼容接口',
    baseUrl: 'https://api.siliconflow.cn/v1',
    models: ['deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1', 'Qwen/Qwen2.5-72B-Instruct']
  },
  {
    value: 'openrouter',
    label: 'OpenRouter',
    summary: '聚合式 OpenAI 兼容路由平台',
    baseUrl: 'https://openrouter.ai/api/v1',
    models: ['openai/gpt-5-mini', 'google/gemini-2.5-pro', 'anthropic/claude-sonnet-4']
  },
  {
    value: 'volcengine',
    label: '火山引擎',
    summary: '火山方舟 OpenAI 兼容接口，模型字段通常填写 Endpoint ID',
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    models: []
  },
  {
    value: 'custom',
    label: '自定义',
    summary: '手动填写兼容接口地址和模型名',
    baseUrl: '',
    models: []
  }
]

const providerMap = Object.fromEntries(providerOptions.map((item) => [item.value, item]))

const loading = ref(false)
const saving = ref(false)
const configForm = ref({
  llmEnabled: false,
  llmProvider: 'custom',
  llmBaseUrl: '',
  llmApiKey: '',
  llmHasApiKey: false,
  clearLlmApiKey: false,
  llmModel: '',
  llmTimeoutSeconds: 12,
  llmTemperature: 0.2,
  llmMaxInputItems: 8
})

const normalizeProvider = (provider) => (providerMap[provider] ? provider : 'custom')

const selectedProvider = computed(() => providerMap[normalizeProvider(configForm.value.llmProvider)] || providerMap.custom)
const providerModels = computed(() => selectedProvider.value.models || [])
const isCustomProvider = computed(() => selectedProvider.value.value === 'custom')
const isVolcengineProvider = computed(() => selectedProvider.value.value === 'volcengine')

const syncProviderPreset = (provider, { forceModel = false } = {}) => {
  const meta = providerMap[normalizeProvider(provider)] || providerMap.custom
  if (meta.value !== 'custom') {
    configForm.value.llmBaseUrl = meta.baseUrl
    if (forceModel || !meta.models.includes(configForm.value.llmModel)) {
      configForm.value.llmModel = meta.models[0] || ''
    }
  }
}

const handleProviderChange = (provider) => {
  syncProviderPreset(provider, { forceModel: true })
}

const loadConfig = async () => {
  loading.value = true
  try {
    const res = await systemApi.getConfig()
    const payload = res.data
    const data = payload?.code === 200 ? (payload.data || {}) : {}
    const provider = normalizeProvider(data.llm_provider || 'custom')
    const preset = providerMap[provider] || providerMap.custom
    const baseUrl = provider === 'custom' ? (data.llm_base_url || '') : (data.llm_base_url || preset.baseUrl)
    const model = data.llm_model || preset.models?.[0] || ''

    configForm.value = {
      llmEnabled: Boolean(data.llm_enabled),
      llmProvider: provider,
      llmBaseUrl: baseUrl,
      llmApiKey: '',
      llmHasApiKey: Boolean(data.llm_has_api_key),
      clearLlmApiKey: false,
      llmModel: model,
      llmTimeoutSeconds: Number(data.llm_timeout_seconds ?? 12),
      llmTemperature: Number(data.llm_temperature ?? 0.2),
      llmMaxInputItems: Number(data.llm_max_input_items ?? 8)
    }

    if (provider !== 'custom' && !configForm.value.llmBaseUrl) {
      syncProviderPreset(provider)
    }
  } catch (error) {
    ElMessage.error('配置加载失败')
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    const res = await systemApi.updateConfig({
      llm_enabled: configForm.value.llmEnabled,
      llm_provider: configForm.value.llmProvider,
      llm_base_url: configForm.value.llmBaseUrl,
      llm_api_key: configForm.value.llmApiKey || undefined,
      clear_llm_api_key: configForm.value.clearLlmApiKey,
      llm_model: configForm.value.llmModel,
      llm_timeout_seconds: configForm.value.llmTimeoutSeconds,
      llm_temperature: configForm.value.llmTemperature,
      llm_max_input_items: configForm.value.llmMaxInputItems
    })
    const payload = res.data
    if (payload.code === 200) {
      ElMessage.success('保存成功')
      await loadConfig()
    } else {
      ElMessage.error(payload.message || '保存失败')
    }
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.system-settings-view {
  min-height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.card-header-title {
  display: grid;
  gap: 4px;
}

.header-desc {
  color: var(--color-text-sec);
  font-size: 13px;
}

.settings-overview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.overview-card,
.section-card {
  background: rgba(255, 255, 255, 0.02);
}

.overview-card {
  display: grid;
  gap: 8px;
  padding: 18px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.overview-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.overview-value {
  font-size: 1.2rem;
}

.overview-tip {
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.6;
}

.section-card {
  margin-bottom: 20px;
}

.form-block {
  width: 100%;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.6;
}

.provider-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-sec);
}

.config-inline-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
}

.note-list {
  display: grid;
  gap: 10px;
}

.note-item {
  color: var(--color-text-main);
  line-height: 1.7;
}

@media (max-width: 960px) {
  .settings-overview {
    grid-template-columns: 1fr;
  }
}
</style>
