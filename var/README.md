# Runtime Workspace

这个目录只存放运行时产物，不存放长期维护的业务代码。

当前约定：

- `var/runtime/`: 默认运行数据库与缓存
- `var/cache/`: 下载模型和本地缓存
- `var/artifacts/`: 可复用产物
- `var/test-runs/`: smoke test 和一次性联调输出
- `var/logs/`: 开发服务日志
- `var/run/`: pid 与状态文件
- `var/legacy/`: 历史运行产物归档

规则：

- 可以清理
- 不应被业务代码硬编码依赖
- 需要通过脚本、环境变量或 summary 文件引用
