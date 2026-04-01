<template>
  <div class="admin-accounts-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">交易账户</div>
            <div class="card-desc">本迭代先完成账户建模、归属绑定和默认账户选择。</div>
          </div>
          <div class="card-actions">
            <el-button @click="loadAccounts">刷新</el-button>
            <el-button type="primary" @click="openCreateDialog">新增账户</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="accounts" style="width: 100%">
        <el-table-column prop="account_code" label="账户编码" min-width="140" />
        <el-table-column prop="account_name" label="账户名称" min-width="160" />
        <el-table-column label="可用金额" min-width="140">
          <template #default="{ row }">
            {{ formatMoney(row.available_cash) }}
          </template>
        </el-table-column>
        <el-table-column prop="owner_display_name" label="归属用户" min-width="160">
          <template #default="{ row }">
            {{ row.owner_display_name || row.owner_username || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button type="success" link @click="switchToAccount(row)">查看</el-button>
            <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
            <el-button type="warning" link @click="openBindDialog(row)">绑定用户</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editDialogVisible" :title="isEdit ? '编辑账户' : '新增账户'" width="520px">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="账户编码" v-if="!isEdit">
          <el-input v-model="editForm.account_code" />
        </el-form-item>
        <el-form-item label="账户名称">
          <el-input v-model="editForm.account_name" />
        </el-form-item>
        <el-form-item label="可用金额">
          <el-input-number v-model="editForm.available_cash" :min="0" :precision="2" :step="10000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width: 100%">
            <el-option label="启用" value="active" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="归属用户" v-if="!isEdit">
          <el-select v-model="editForm.owner_user_id" clearable style="width: 100%">
            <el-option
              v-for="user in users"
              :key="user.id"
              :label="`${user.display_name} (${user.username})`"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bindDialogVisible" title="绑定用户" width="480px">
      <el-form :model="bindForm" label-width="100px">
        <el-form-item label="目标用户">
          <el-select v-model="bindForm.user_id" clearable style="width: 100%">
            <el-option
              v-for="user in users"
              :key="user.id"
              :label="`${user.display_name} (${user.username})`"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="bindForm.set_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bindDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="binding" @click="submitBind">确认绑定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminApi } from '../api'
import { setCurrentAccount } from '../auth'

const loading = ref(false)
const saving = ref(false)
const binding = ref(false)
const isEdit = ref(false)
const editingId = ref('')
const bindingAccountId = ref('')
const accounts = ref([])
const users = ref([])
const editDialogVisible = ref(false)
const bindDialogVisible = ref(false)
const editForm = reactive({
  account_code: '',
  account_name: '',
  available_cash: 1000000,
  owner_user_id: '',
  status: 'active',
})
const bindForm = reactive({
  user_id: '',
  set_default: true,
})

const loadUserOptions = async () => {
  if (users.value.length) {
    return
  }
  const usersResponse = await adminApi.listUsers()
  users.value = usersResponse.data?.data?.users || []
}

const loadAccounts = async () => {
  loading.value = true
  try {
    const accountsResponse = await adminApi.listAccounts()
    accounts.value = accountsResponse.data?.data?.accounts || []
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '加载账户列表失败')
  } finally {
    loading.value = false
  }
}

const resetEditForm = () => {
  editingId.value = ''
  editForm.account_code = ''
  editForm.account_name = ''
  editForm.available_cash = 1000000
  editForm.owner_user_id = ''
  editForm.status = 'active'
}

const openCreateDialog = async () => {
  isEdit.value = false
  resetEditForm()
  try {
    await loadUserOptions()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '加载用户选项失败')
    return
  }
  editDialogVisible.value = true
}

const openEditDialog = (row) => {
  isEdit.value = true
  editingId.value = row.id
  editForm.account_code = row.account_code
  editForm.account_name = row.account_name
  editForm.available_cash = Number(row.available_cash ?? 1000000)
  editForm.owner_user_id = row.owner_user_id || ''
  editForm.status = row.status
  editDialogVisible.value = true
}

const openBindDialog = async (row) => {
  bindingAccountId.value = row.id
  bindForm.user_id = row.owner_user_id || ''
  bindForm.set_default = true
  try {
    await loadUserOptions()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '加载用户选项失败')
    return
  }
  bindDialogVisible.value = true
}

const submitEdit = async () => {
  saving.value = true
  try {
    if (isEdit.value) {
      await adminApi.updateAccount(editingId.value, {
        account_name: editForm.account_name,
        available_cash: Number(editForm.available_cash ?? 0),
        status: editForm.status,
      })
      ElMessage.success('账户已更新')
    } else {
      await adminApi.createAccount({
        account_code: editForm.account_code,
        account_name: editForm.account_name,
        available_cash: Number(editForm.available_cash ?? 0),
        owner_user_id: editForm.owner_user_id || null,
        status: editForm.status,
      })
      ElMessage.success('账户已创建')
    }
    editDialogVisible.value = false
    await loadAccounts()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '保存账户失败')
  } finally {
    saving.value = false
  }
}

const submitBind = async () => {
  binding.value = true
  try {
    await adminApi.bindAccount(bindingAccountId.value, {
      user_id: bindForm.user_id || null,
      set_default: Boolean(bindForm.set_default),
    })
    ElMessage.success('账户绑定已更新')
    bindDialogVisible.value = false
    await loadAccounts()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '绑定账户失败')
  } finally {
    binding.value = false
  }
}

const switchToAccount = (row) => {
  setCurrentAccount({
    id: row.id,
    account_code: row.account_code,
    account_name: row.account_name,
    owner_user_id: row.owner_user_id,
    status: row.status,
  })
  ElMessage.success(`已切换查看账户：${row.account_name}`)
  window.location.href = '/account'
}

const formatMoney = (value) => {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

onMounted(() => {
  loadAccounts()
})
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.card-desc {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.card-actions {
  display: flex;
  gap: 10px;
}
</style>
