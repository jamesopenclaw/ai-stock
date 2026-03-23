<template>
  <view class="page">
    <view class="card hero-card">
      <text class="page-title">系统设置</text>
      <text class="page-desc">优先用供应商预设管理 LLM 接入。常见平台直接下拉切换，自定义平台再手动填地址。</text>
    </view>

    <view class="card">
      <view class="card-title">当前状态</view>
      <view class="info-row">
        <text class="info-label">LLM 辅助</text>
        <text class="info-value">{{ configForm.llmEnabled ? '已启用' : '未启用' }}</text>
      </view>
      <view class="info-row">
        <text class="info-label">供应商</text>
        <text class="info-value">{{ selectedProvider.label }}</text>
      </view>
      <view class="info-row">
        <text class="info-label">模型名称</text>
        <text class="info-value">{{ configForm.llmModel || '未设置' }}</text>
      </view>
      <view class="info-row">
        <text class="info-label">密钥状态</text>
        <text class="info-value">{{ configForm.llmHasApiKey ? '已保存' : '未保存' }}</text>
      </view>
    </view>

    <view class="card">
      <view class="card-title">模型接入</view>
      <view class="form-item">
        <text class="form-label">启用 LLM 辅助</text>
        <switch :checked="configForm.llmEnabled" @change="onLlmEnabledChange" color="#409eff" />
      </view>

      <view class="form-item">
        <text class="form-label">供应商</text>
        <picker :range="providerLabels" :value="providerIndex" @change="onProviderPickerChange">
          <view class="picker-value">{{ selectedProvider.label }}</view>
        </picker>
        <text class="form-help">{{ selectedProvider.summary }}</text>
      </view>

      <view class="form-item">
        <text class="form-label">模型名称</text>
        <picker
          v-if="providerModels.length"
          :range="providerModels"
          :value="modelIndex"
          @change="onModelPickerChange"
        >
          <view class="picker-value">{{ configForm.llmModel || '请选择模型' }}</view>
        </picker>
        <input
          v-else
          class="form-input"
          v-model="configForm.llmModel"
          :placeholder="isVolcengineProvider ? '请输入火山方舟 Endpoint ID' : '请输入模型名'"
        />
        <text class="form-help">
          {{
            providerModels.length
              ? '常用模型已内置到下拉框，自定义平台请手动填写。'
              : isVolcengineProvider
                ? '火山引擎通常填写你在方舟里创建的推理接入点 Endpoint ID。'
                : '自定义供应商请手动填写模型名。'
          }}
        </text>
      </view>

      <view class="form-item">
        <text class="form-label">Base URL</text>
        <input
          class="form-input"
          v-model="configForm.llmBaseUrl"
          :disabled="!isCustomProvider"
          :placeholder="isCustomProvider ? '请输入兼容接口地址' : '供应商预设自动填写'"
        />
        <text class="form-help">
          {{ isCustomProvider ? '自定义模式下手动填写接口地址。' : '当前是供应商预设地址，切换供应商会自动更新。' }}
        </text>
      </view>

      <view class="form-item">
        <text class="form-label">API Key</text>
        <input class="form-input" v-model="configForm.llmApiKey" password placeholder="留空则保持不变" />
        <text class="form-help" v-if="configForm.llmHasApiKey && !configForm.clearLlmApiKey">数据库已保存密钥</text>
      </view>

      <view class="form-item">
        <text class="form-label">清空已存密钥</text>
        <switch :checked="configForm.clearLlmApiKey" @change="onClearApiKeyChange" color="#f56c6c" />
      </view>
    </view>

    <view class="card">
      <view class="card-title">运行参数</view>
      <view class="form-item">
        <text class="form-label">超时秒数</text>
        <input class="form-input" v-model="configForm.llmTimeoutSeconds" type="digit" placeholder="如: 12" />
      </view>
      <view class="form-item">
        <text class="form-label">温度</text>
        <input class="form-input" v-model="configForm.llmTemperature" type="digit" placeholder="0 ~ 2" />
      </view>
      <view class="form-item">
        <text class="form-label">输入条数</text>
        <input class="form-input" v-model="configForm.llmMaxInputItems" type="number" placeholder="1 ~ 20" />
      </view>
      <view class="form-help">解释型任务建议保持低温度，并限制单次输入条数控制成本和延迟。</view>
    </view>

    <view class="action-bar">
      <view class="btn-save" @click="saveConfig">保存设置</view>
    </view>

    <view v-if="loading" class="loading">
      <text>加载中...</text>
    </view>
  </view>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { accountApi } from '../../api'

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
const providerLabels = providerOptions.map((item) => item.label)

const loading = ref(false)
const configForm = ref({
  llmEnabled: false,
  llmProvider: 'custom',
  llmBaseUrl: '',
  llmApiKey: '',
  llmHasApiKey: false,
  clearLlmApiKey: false,
  llmModel: '',
  llmTimeoutSeconds: '12',
  llmTemperature: '0.2',
  llmMaxInputItems: '8'
})

const normalizeProvider = (provider) => (providerMap[provider] ? provider : 'custom')

const selectedProvider = computed(() => providerMap[normalizeProvider(configForm.value.llmProvider)] || providerMap.custom)
const providerModels = computed(() => selectedProvider.value.models || [])
const isCustomProvider = computed(() => selectedProvider.value.value === 'custom')
const isVolcengineProvider = computed(() => selectedProvider.value.value === 'volcengine')
const providerIndex = computed(() => providerOptions.findIndex((item) => item.value === normalizeProvider(configForm.value.llmProvider)))
const modelIndex = computed(() => {
  const index = providerModels.value.findIndex((item) => item === configForm.value.llmModel)
  return index >= 0 ? index : 0
})

const syncProviderPreset = (provider, { forceModel = false } = {}) => {
  const meta = providerMap[normalizeProvider(provider)] || providerMap.custom
  if (meta.value !== 'custom') {
    configForm.value.llmBaseUrl = meta.baseUrl
    if (forceModel || !meta.models.includes(configForm.value.llmModel)) {
      configForm.value.llmModel = meta.models[0] || ''
    }
  }
}

const onLlmEnabledChange = (e) => {
  configForm.value.llmEnabled = Boolean(e.detail.value)
}

const onClearApiKeyChange = (e) => {
  configForm.value.clearLlmApiKey = Boolean(e.detail.value)
}

const onProviderPickerChange = (e) => {
  const provider = providerOptions[Number(e.detail.value)]?.value || 'custom'
  configForm.value.llmProvider = provider
  syncProviderPreset(provider, { forceModel: true })
}

const onModelPickerChange = (e) => {
  configForm.value.llmModel = providerModels.value[Number(e.detail.value)] || ''
}

const loadConfig = async () => {
  loading.value = true
  try {
    const res = await accountApi.getConfig()
    const data = res.data || {}
    const provider = normalizeProvider(data.llm_provider || 'custom')
    const preset = providerMap[provider] || providerMap.custom
    configForm.value = {
      llmEnabled: Boolean(data.llm_enabled),
      llmProvider: provider,
      llmBaseUrl: provider === 'custom' ? (data.llm_base_url || '') : (data.llm_base_url || preset.baseUrl),
      llmApiKey: '',
      llmHasApiKey: Boolean(data.llm_has_api_key),
      clearLlmApiKey: false,
      llmModel: data.llm_model || preset.models?.[0] || '',
      llmTimeoutSeconds: String(data.llm_timeout_seconds ?? 12),
      llmTemperature: String(data.llm_temperature ?? 0.2),
      llmMaxInputItems: String(data.llm_max_input_items ?? 8)
    }
  } catch (e) {
    uni.showToast({ title: '配置加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  loading.value = true
  try {
    const res = await accountApi.updateConfig({
      llm_enabled: configForm.value.llmEnabled,
      llm_provider: configForm.value.llmProvider,
      llm_base_url: configForm.value.llmBaseUrl,
      llm_api_key: configForm.value.llmApiKey || undefined,
      clear_llm_api_key: configForm.value.clearLlmApiKey,
      llm_model: configForm.value.llmModel,
      llm_timeout_seconds: parseFloat(configForm.value.llmTimeoutSeconds || '12'),
      llm_temperature: parseFloat(configForm.value.llmTemperature || '0.2'),
      llm_max_input_items: parseInt(configForm.value.llmMaxInputItems || '8', 10)
    })

    if (res.code === 200) {
      uni.showToast({ title: '保存成功', icon: 'success' })
      await loadConfig()
    } else {
      uni.showToast({ title: res.message || '保存失败', icon: 'none' })
    }
  } catch (e) {
    uni.showToast({ title: '保存失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.page { padding: 10px; background: #f5f7fb; min-height: 100vh; }
.card { background: #fff; border-radius: 10px; padding: 15px; margin-bottom: 10px; }
.hero-card { display: flex; flex-direction: column; gap: 8px; }
.page-title { font-size: 18px; font-weight: bold; }
.page-desc { font-size: 13px; color: #666; line-height: 1.6; }
.card-title { font-size: 16px; font-weight: bold; margin-bottom: 12px; }
.info-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f1f1; }
.info-row:last-child { border-bottom: none; }
.info-label, .form-label { color: #666; font-size: 14px; }
.info-value { font-weight: bold; color: #222; }
.form-item { margin-bottom: 14px; display: flex; flex-direction: column; gap: 8px; }
.form-input,
.picker-value { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; background: #fff; box-sizing: border-box; color: #222; }
.form-input[disabled] { background: #f5f7fb; color: #666; }
.form-help { font-size: 12px; color: #67c23a; line-height: 1.6; }
.action-bar { margin-top: 10px; }
.btn-save { padding: 12px; text-align: center; background: #409eff; color: #fff; border-radius: 8px; font-size: 14px; }
.loading { text-align: center; padding: 30px; color: #999; }
</style>
