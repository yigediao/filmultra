# 开发治理说明

这个目录存放长期有效的开发约定，而不是一次性的实验记录。

## 目标

- 把业务代码、临时测试、运行产物、外部依赖分开
- 降低“项目能跑但无法维护”的风险
- 让后续开发能快速判断某个文件属于长期代码还是临时实验

## 现在执行的治理规则

### 1. 长期代码

长期维护的业务代码只放在这些区域：

- `backend/app/`
- `frontend/app/`
- `frontend/components/`
- `frontend/lib/`
- `docs/`

### 2. 临时测试代码

临时验证、smoke test、一次性联调脚本遵循：

- 入口脚本优先放 `scripts/smoke/`
- 开发辅助脚本优先放 `scripts/dev/`
- 脚本可以存在，但输出不能污染业务目录

### 3. 运行产物

运行产物统一写入 `var/`：

- `var/runtime/backend/`: 默认后端数据库与预览缓存
- `var/cache/backend/`: 模型缓存
- `var/artifacts/`: 3D 重建等可复用产物
- `var/test-runs/`: 一次性测试运行结果
- `var/logs/`: 开发栈和脚本日志
- `var/run/`: pid、状态文件
- `var/legacy/`: 历史运行产物归档

不要再把新的测试数据库、后端日志、预览缓存直接写进 `backend/` 根目录。

### 4. 开发日志

每次实质性改动后，在 `WORKLOG.md` 记录：

- 日期
- 本次目标
- 关键改动
- 验证结果
- 未完成项或风险

### 5. 文档更新顺序

涉及结构或流程变化时，按这个顺序维护：

1. `README.md`
2. `docs/development/REPO_LAYOUT.md`
3. `docs/development/WORKLOG.md`
4. 必要时补充专项文档

## 当前遗留问题

这些区域目前仍然存在，但属于历史遗留或本机样本区：

- `.gvfs_mounts/`
- `.smb_stage/`
- `2026-3-7/`

后续不再新增类似落盘方式，逐步收敛到 `var/`。

建议定期执行：

```bash
make migrate-workspace
make project-status
```
