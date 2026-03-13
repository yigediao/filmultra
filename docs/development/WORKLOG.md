# 开发日志

## 记录规则

- 每次实质性变更都追加新条目
- 使用绝对日期，例如 `2026-03-11`
- 写清楚目标、改动、验证和遗留风险

## 2026-03-11

### 项目治理基线

目标：
建立长期开发的基础治理层，把长期代码、临时测试和运行产物分开。

改动：

- 新增根目录 `README.md`，把项目入口、目录职责和常用命令收口
- 新增 `.gitignore`，忽略本机挂载、运行产物、数据库、日志、Node 和 Python 缓存
- 新增 `.editorconfig`，统一基础格式约定
- 新增 `Makefile`，提供开发、smoke test、联调栈的固定入口
- 后端默认运行路径改为 `var/runtime/backend`、`var/cache/backend`、`var/artifacts`
- 新增 `backend/.env.example`
- 新增 `docs/development/README.md` 和 `docs/development/REPO_LAYOUT.md`
- 新增 `var/` 目录说明，明确运行产物归档位置
- 新增工作区迁移脚本和状态脚本

验证：

- `make help` 可输出固定入口
- 新脚本路径通过 `bash -n` 校验
- `make smoke-synology-gvfs` 已生成隔离运行目录：
  `var/test-runs/synology-gvfs/20260311010921_photo_byyear_2026_2_28_/`
- `make review-synology-gvfs` 和 `make stop-review-synology-gvfs` 已完成启停验证
- `make migrate-workspace` 已把旧 backend 运行产物迁入 `var/`
- `make project-status` 可输出当前管理状态
- 当前归档目录：`var/legacy/backend-runtime/20260311223238/`
- `make project-status` 结果中 `Backend legacy leftovers` 为 `(none)`

遗留项：

- 根目录仍有本机样本目录 `2026-3-7/`，暂未迁移

### 群晖 GVFS 联调基线

目标：
把群晖目录 smoke test 与前端联调变成可重复、可回看、可清理的流程。

改动：

- Synology GVFS smoke test 输出改为落在 `var/test-runs/synology-gvfs/<run-id>/`
- 每次运行生成独立 `summary.json`
- 新增 `scripts/dev/start_synology_gvfs_review_stack.sh`
- 新增 `scripts/dev/stop_synology_gvfs_review_stack.sh`
- review stack 改为 detached 方式启动，并由 pid/进程组统一回收

验证：

- 最近一次群晖 smoke test 已能返回资产列表和预览图
- 前端可通过固定 review stack 命令连接到测试后端
- `make stop-review-synology-gvfs` 后端口 `3001/8012` 已确认释放

遗留项：

- 真实业务代码默认路径仍然以 `/mnt/photo_library` 为主
- GNOME 文件管理器对群晖根共享枚举仍有兼容性问题，直连共享可用

## 2026-03-12

### 中断任务恢复

目标：
修复 review stack 重启后，旧的 `scan` / `face_detect` 任务长期卡在 `running`，导致首页同步状态错误的问题。

改动：

- 新增启动恢复逻辑 `backend/app/core/job_recovery.py`
- 后端启动时会把上一次进程遗留的 `pending` / `running` 任务统一标记为 `failed`
- 为被恢复的任务写入明确错误信息，说明这是上次进程中断导致的残留状态

验证：

- 重启 review stack 后，历史卡死的 `scan` 和 `face_detect` 任务已从 `running` 变为 `failed`
- `/api/assets/state` 中 `active_scan_jobs` 已从 `1` 变为 `0`
- 当前前后端联调栈可正常启动，`3001/8012` 可访问

遗留项：

- 这次测试数据库里没有真正完成态的 `scan` 任务，因此 `last_completed_scan_at` 仍为 `null`
- 任务执行模型仍然是进程内 background task，后续仍应迁移到独立 worker

### 联调栈稳定化

目标：
修复首页在 review 环境下间歇性返回 `500`，并把 smoke 与 review 的端口职责拆开，避免开发链路互相污染。

改动：

- `scripts/dev/start_synology_gvfs_review_stack.sh` 改为先执行 `next build`，再以 `next start` 启动 review 前端
- 每次 review 启动前清理 `frontend/.next`，降低 Next.js dev manifest 残留导致的随机崩溃
- 新增 `frontend-build.log`，把前端构建日志与运行日志分离
- `Makefile` 新增 `REVIEW_API_PORT` / `REVIEW_FRONTEND_PORT`，review 默认端口固定回 `8012/3001`
- smoke test 仍使用 `TEST_API_PORT=8013`，与 review 栈隔离

验证：

- `make review-synology-gvfs` 可重新拉起稳定 review 栈
- 首页 `/`、人物页 `/people`、待确认页 `/people/review` 均已返回 `200`
- 最新 review 数据可读：`362` 资产、`724` 文件、`741` 张人脸、`19` 个 cluster

遗留项：

- review 栈每次启动都需要重新构建前端，启动时间会比 `next dev` 更长
