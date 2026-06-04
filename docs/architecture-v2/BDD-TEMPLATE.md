# Aegis-Manim BDD 文档模板

## Phase 命名规范

- **P0**: Provider 稳定性与可用性
- **P1**: 测试自动化与监控
- **P2**: 社区与交付功能
- **P3**: 渲染与性能优化

每个 Phase 内按字母编号：`P0-A`, `P0-B`, `P1-A`, `P1-B`...

---

## 文档结构

```markdown
# Phase {ID}: {Feature Name}

## 背景

{为什么需要这个功能，解决什么问题}

## BDD 用例

### 用例 1: {场景描述}

**Given** {前置条件}
**When** {用户行为/系统事件}
**Then** {预期结果}
**And** {额外断言}

### 用例 2: ...

## 技术设计

### 新增/修改文件

- `path/to/file.py` — {作用}

### API 变更

- `METHOD /path` — {变更内容}

### 状态机

- `{status}` → `{status}` via `{action}`

## 手动验收入口

- {URL 或命令}

## 验收标准

- [ ] {检查项 1}
- [ ] {检查项 2}
```

---

## 证据等级

| 等级 | 含义 |
|------|------|
| `production_verified` | 生产环境验证通过 |
| `production_unstable` | 生产环境可用但不稳定 |
| `staging_verified` | 预发布环境验证通过 |
| `local_execution` | 本地执行验证通过 |
| `local_file` | 本地文件/配置验证 |
| `unverified` | 未验证 |
