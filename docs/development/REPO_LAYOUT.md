# 仓库分层约定

## 主要目录

### `backend/`

- `backend/app/`: 后端业务代码
- `backend/requirements.txt`: 后端依赖
- `backend/Dockerfile`: 后端镜像定义

### `frontend/`

- `frontend/app/`: Next.js 路由页面
- `frontend/components/`: 组件
- `frontend/lib/`: API 与类型层

### `docs/`

- 长期有效的架构、环境、开发治理文档

### `scripts/`

- `scripts/dev/`: 长期保留的开发辅助脚本
- `scripts/smoke/`: 临时验证和 smoke test 脚本
- `scripts/` 根目录：兼容旧入口，逐步迁移中

### `var/`

- 运行时产物，不属于长期代码
- 允许清理和轮换
- `var/runtime/`: 默认运行数据
- `var/cache/`: 下载模型和本地缓存
- `var/artifacts/`: 可复用产物
- `var/test-runs/`: 临时验证结果
- `var/legacy/`: 历史归档

### `third_party/`

- 外部仓库或上游源码

## 文件放置规则

### 业务逻辑

如果改动会直接影响产品行为，应优先进入：

- `backend/app/`
- `frontend/app/`
- `frontend/components/`
- `frontend/lib/`

### 本机开发脚本

如果脚本用于：

- 启动联调环境
- 停止本地开发栈
- 打印最近测试结果

放入 `scripts/dev/`。

### smoke test

如果脚本用于：

- 挂载目录验证
- 单次链路探测
- 模型环境检查

优先放入 `scripts/smoke/`，并把输出写到 `var/test-runs/`。

## 当前本机例外

下面这些目录不是长期代码区，不应被业务代码硬编码依赖：

- `.gvfs_mounts/`
- `.smb_stage/`
- `2026-3-7/`

如果必须使用这些目录做测试，应通过：

- 环境变量
- CLI 参数
- smoke test summary 文件

来传入，而不是写死在业务逻辑里。
