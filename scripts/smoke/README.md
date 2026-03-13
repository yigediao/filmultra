# Smoke Scripts

这个目录存放一次性验证和短链路 smoke test。

规则：

- 输出统一写到 `var/test-runs/`
- 脚本可以被长期保留，但不应把产物写回业务目录
- 根目录 `scripts/` 下如有同名脚本，视为兼容旧入口的 wrapper
