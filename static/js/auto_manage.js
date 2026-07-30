// 加载任务列表
async function loadTasks() {
  try {
    const res = await fetch('/api/auto/tasks');
    const tasks = await res.json();
    const tbody = document.getElementById('taskTable');
    if (!tasks.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">暂无自动任务</td></tr>';
      return;
    }
    tbody.innerHTML = tasks.map(function(t) {
      var stepText = t.steps_max ? t.steps_min + ' ~ ' + t.steps_max : t.steps_min + ' (固定)';
      var statusBadge = '<span class="badge ' + (t.enabled ? 'badge-success' : 'badge-secondary') + '">' + (t.enabled ? '启用' : '停用') + '</span>';
      if (t.last_sync_status) {
        statusBadge += ' <span class="badge ' + (t.last_sync_status === 'success' ? 'badge-success' : 'badge-danger') + ' ms-1">' + (t.last_sync_status === 'success' ? '成功' : '失败') + '</span>';
      }
      var lastTime = t.last_sync_time || '-';
      var actions = '<button class="btn btn-sm btn-outline-primary" data-act="run" data-id="' + t.id + '" title="立即执行"><i class="bi bi-play"></i></button> '
        + '<button class="btn btn-sm btn-outline-warning" data-act="toggle" data-id="' + t.id + '" title="启用/停用"><i class="bi bi-power"></i></button> '
        + '<button class="btn btn-sm btn-outline-secondary" data-act="edit" data-id="' + t.id + '" title="编辑"><i class="bi bi-pencil"></i></button> '
        + '<button class="btn btn-sm btn-outline-danger" data-act="delete" data-id="' + t.id + '" title="删除"><i class="bi bi-trash"></i></button>';
      return '<tr><td>' + t.username + '</td><td>' + stepText + '</td><td>每天 ' + t.exec_hours + ' 点 / ' + t.exec_minute + '分</td><td>' + statusBadge + '</td><td>' + lastTime + '</td><td>' + actions + '</td></tr>';
    }).join('');
  } catch(e) {
    console.error('loadTasks error:', e);
  }
}

// 新增任务 - 重置表单
function openAdd() {
  document.getElementById('modalTitle').textContent = '新增自动任务（Zepp Life 刷步）';
  document.getElementById('taskId').value = '';
  document.getElementById('username').value = '';
  document.getElementById('username').disabled = false;
  document.getElementById('password').value = '';
  document.getElementById('password').placeholder = '账号密码';
  document.getElementById('stepsMin').value = '';
  document.getElementById('stepsMax').value = '';
  document.getElementById('execHours').value = '8';
  document.getElementById('execMinute').value = '0';
  document.getElementById('enabled').checked = true;
}

// 编辑任务
async function openEdit(id) {
  const res = await fetch('/api/auto/tasks');
  const tasks = await res.json();
  const t = tasks.find(function(x) { return x.id === id; });
  if (!t) return;
  document.getElementById('modalTitle').textContent = '编辑自动任务（Zepp Life 刷步）';
  document.getElementById('taskId').value = t.id;
  document.getElementById('username').value = t.username;
  document.getElementById('username').disabled = true;
  document.getElementById('password').value = '';
  document.getElementById('password').placeholder = '留空则不修改密码';
  document.getElementById('stepsMin').value = t.steps_min;
  document.getElementById('stepsMax').value = t.steps_max || '';
  document.getElementById('execHours').value = t.exec_hours;
  document.getElementById('execMinute').value = t.exec_minute;
  document.getElementById('enabled').checked = t.enabled;
  new bootstrap.Modal(document.getElementById('taskModal')).show();
}

// 保存任务
async function saveTask() {
  const id = document.getElementById('taskId').value;
  const body = {
    username: document.getElementById('username').value,
    password: document.getElementById('password').value,
    steps_min: document.getElementById('stepsMin').value,
    steps_max: document.getElementById('stepsMax').value,
    exec_hours: document.getElementById('execHours').value,
    exec_minute: document.getElementById('execMinute').value,
    enabled: document.getElementById('enabled').checked
  };
  const url = id ? '/api/auto/tasks/' + id : '/api/auto/tasks';
  const method = id ? 'PUT' : 'POST';
  const res = await fetch(url, { method: method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();
  showToast(data.message, data.success);
  if (data.success) {
    bootstrap.Modal.getInstance(document.getElementById('taskModal')).hide();
    loadTasks();
  }
}

// 启用/停用
async function toggleTask(id) {
  const res = await fetch('/api/auto/tasks/' + id + '/toggle', { method: 'POST' });
  const data = await res.json();
  showToast(data.message, data.success);
  loadTasks();
}

// 立即执行
async function runNow(id) {
  if (!confirm('确认立即执行该任务？')) return;
  showToast('正在执行...', true);
  const res = await fetch('/api/auto/tasks/' + id + '/run', { method: 'POST' });
  const data = await res.json();
  showToast(data.message, data.success);
  loadTasks();
}

// 删除任务
async function deleteTask(id) {
  if (!confirm('确认删除该任务？')) return;
  const res = await fetch('/api/auto/tasks/' + id, { method: 'DELETE' });
  const data = await res.json();
  showToast(data.message, data.success);
  loadTasks();
}

// Toast 提示
function showToast(msg, success) {
  const el = document.getElementById('toast');
  el.innerHTML = '<div class="toast show align-items-center text-white ' + (success ? 'bg-success' : 'bg-danger') + '" role="alert">'
    + '<div class="d-flex"><div class="toast-body">' + msg + '</div>'
    + '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-dismiss="toast"></button></div></div>';
  setTimeout(function() { el.innerHTML = ''; }, 4000);
}

// 统一事件绑定（替代所有 inline onclick）
document.addEventListener('DOMContentLoaded', function() {
  // 加载任务列表
  loadTasks();

  // 新增按钮 - 重置表单后让 Bootstrap 打开弹窗
  var btnAdd = document.getElementById('btnAddTask');
  if (btnAdd) {
    btnAdd.addEventListener('click', function() {
      openAdd();
    });
  }

  // 保存按钮
  var btnSave = document.getElementById('btnSaveTask');
  if (btnSave) {
    btnSave.addEventListener('click', saveTask);
  }

  // 刷新按钮
  var btnRefresh = document.getElementById('btnRefresh');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', loadTasks);
  }

  // 任务列表中的操作按钮（事件委托）
  var taskTable = document.getElementById('taskTable');
  if (taskTable) {
    taskTable.addEventListener('click', function(e) {
      var btn = e.target.closest('button[data-act]');
      if (!btn) return;
      var act = btn.getAttribute('data-act');
      var id = btn.getAttribute('data-id');
      if (act === 'run') runNow(id);
      else if (act === 'toggle') toggleTask(id);
      else if (act === 'edit') openEdit(parseInt(id));
      else if (act === 'delete') deleteTask(id);
    });
  }

  // toast 关闭按钮（事件委托）
  var toastEl = document.getElementById('toast');
  if (toastEl) {
    toastEl.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-dismiss="toast"]');
      if (btn) {
        var toast = btn.closest('.toast');
        if (toast) toast.remove();
      }
    });
  }
});
