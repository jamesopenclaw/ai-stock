<template>
  <div class="admin-users-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">用户管理</div>
            <div class="card-desc">迭代二先补用户与默认账户绑定能力。</div>
          </div>
          <div class="card-actions">
            <el-button @click="loadUsers">刷新</el-button>
            <el-button type="primary" @click="openCreateDialog">新增用户</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="users" style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="display_name" label="显示名" min-width="140" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'success'">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="default_account_name" label="默认账户" min-width="160" />
        <el-table-column label="最近登录" min-width="180">
          <template #default="{ row }">
            {{ row.last_login_at || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
            <el-button type="warning" link @click="openResetPasswordDialog(row)">重置密码</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑用户' : '新增用户'" width="520px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="用户名" v-if="!isEdit">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码" v-if="!isEdit">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="form.display_name" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="启用" value="active" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认账户">
          <el-select v-model="form.default_account_id" clearable style="width: 100%">
            <el-option
              v-for="account in accounts"
              :key="account.id"
              :label="`${account.account_name} (${account.account_code})`"
              :value="account.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="passwordDialogVisible" title="重置登录密码" width="420px">
      <el-form :model="passwordForm" label-width="100px">
        <el-form-item label="用户">
          <el-input :model-value="passwordTargetName" disabled />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="passwordSaving" @click="submitResetPassword">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminApi } from '../api'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const passwordDialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref('')
const passwordTargetId = ref('')
const passwordTargetName = ref('')
const users = ref([])
const accounts = ref([])
const form = reactive({
  username: '',
  password: '',
  display_name: '',
  role: 'user',
  status: 'active',
  default_account_id: '',
})
const passwordSaving = ref(false)
const passwordForm = reactive({
  password: '',
  confirm_password: '',
})

const resetForm = () => {
  editingId.value = ''
  form.username = ''
  form.password = ''
  form.display_name = ''
  form.role = 'user'
  form.status = 'active'
  form.default_account_id = ''
}

const resetPasswordForm = () => {
  passwordTargetId.value = ''
  passwordTargetName.value = ''
  passwordForm.password = ''
  passwordForm.confirm_password = ''
}

const loadAccountOptions = async () => {
  if (accounts.value.length) {
    return
  }
  const accountsResponse = await adminApi.listAccounts()
  accounts.value = accountsResponse.data?.data?.accounts || []
}

const loadUsers = async () => {
  loading.value = true
  try {
    const usersResponse = await adminApi.listUsers()
    users.value = usersResponse.data?.data?.users || []
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

const openCreateDialog = async () => {
  isEdit.value = false
  resetForm()
  try {
    await loadAccountOptions()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '加载账户选项失败')
    return
  }
  dialogVisible.value = true
}

const openEditDialog = async (row) => {
  isEdit.value = true
  editingId.value = row.id
  form.username = row.username
  form.password = ''
  form.display_name = row.display_name
  form.role = row.role
  form.status = row.status
  form.default_account_id = row.default_account_id || ''
  try {
    await loadAccountOptions()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '加载账户选项失败')
    return
  }
  dialogVisible.value = true
}

const openResetPasswordDialog = (row) => {
  resetPasswordForm()
  passwordTargetId.value = row.id
  passwordTargetName.value = row.display_name || row.username
  passwordDialogVisible.value = true
}

const submitForm = async () => {
  saving.value = true
  try {
    if (isEdit.value) {
      await adminApi.updateUser(editingId.value, {
        display_name: form.display_name,
        role: form.role,
        status: form.status,
        default_account_id: form.default_account_id || null,
      })
      ElMessage.success('用户已更新')
    } else {
      await adminApi.createUser({
        username: form.username,
        password: form.password,
        display_name: form.display_name,
        role: form.role,
        status: form.status,
        default_account_id: form.default_account_id || null,
      })
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await loadUsers()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '保存用户失败')
  } finally {
    saving.value = false
  }
}

const submitResetPassword = async () => {
  if (!passwordForm.password) {
    ElMessage.error('请输入新密码')
    return
  }
  if (passwordForm.password.length < 6) {
    ElMessage.error('新密码至少 6 位')
    return
  }
  if (passwordForm.password !== passwordForm.confirm_password) {
    ElMessage.error('两次输入的密码不一致')
    return
  }

  passwordSaving.value = true
  try {
    await adminApi.resetUserPassword(passwordTargetId.value, {
      password: passwordForm.password,
    })
    ElMessage.success('登录密码已重置，用户需使用新密码重新登录')
    passwordDialogVisible.value = false
    resetPasswordForm()
  } catch (error) {
    ElMessage.error(error.response?.data?.message || '重置密码失败')
  } finally {
    passwordSaving.value = false
  }
}

onMounted(() => {
  loadUsers()
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
