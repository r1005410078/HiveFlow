# Skills 纳入版本控制 + `hiveflow skills` 安装命令

**日期**：2026-03-17
**状态**：已通过用户确认

---

## 背景

当前两个 hiveflow skills（`hiveflow-daily-check`、`hiveflow-portfolio-advisor`）只存在于 `~/.agents/skills/`，未纳入版本控制，无法在多台机器或多个智能体平台之间共享。

问题：
1. 无法跨机器同步 skills（换新电脑需要手动重建）
2. Skills 修改无法追溯历史版本
3. 贡献者/协作者无法获取最新 skills

---

## 设计目标

- Skills 纳入项目仓库 `skills/` 目录，与代码同步维护
- 新增 `hiveflow skills list` + `hiveflow skills install` 命令
- 安装方式为**软链接**（`~/.agents/skills/<name>` → `<project>/skills/<name>`），修改 skill 文件后无需重新安装
- 其他平台（Cursor、自建 Agent 等）自行软链接到 `~/.agents/skills/`

---

## 架构

```
strat-flow/
  skills/                               ← 版本控制在项目中
    hiveflow-daily-check/
      SKILL.md
    hiveflow-portfolio-advisor/
      SKILL.md
  src/hiveflow/
    application/
      skills.py                         ← 业务逻辑（list/install）
    cli.py                              ← 增加 skills 命令组
  tests/
    test_skills.py
```

```
~/.agents/skills/
  hiveflow-daily-check     →  ~/strat-flow/skills/hiveflow-daily-check  (软链接)
  hiveflow-portfolio-advisor →  ~/strat-flow/skills/hiveflow-portfolio-advisor  (软链接)

其他平台（Cursor 等）各自软链接到 ~/.agents/skills/ 统一目录
```

---

## CLI 命令

```bash
hiveflow skills list                        # 列出项目内所有 skill 及安装状态
hiveflow skills install                     # 安装全部（软链接到 ~/.agents/skills/）
hiveflow skills install hiveflow-daily-check  # 安装单个
hiveflow skills install --force             # 强制覆盖已存在的目录
```

### `hiveflow skills list` 示例输出

```
Skills（技能包）

  名称                          状态
  hiveflow-daily-check        ✓ 已安装
  hiveflow-portfolio-advisor  ✗ 未安装

目标目录：~/.agents/skills/
运行 'hiveflow skills install' 安装全部
```

---

## 安装逻辑

每个 skill 的安装行为：

| target 路径状态 | 行为 |
|---|---|
| 不存在 | 创建软链接 ✓ |
| 已是指向正确 source 的软链接 | 跳过（已安装）|
| 软链接指向其他路径 | 警告跳过；`--force` 时删除并重建 |
| 真实目录（非软链接） | 警告跳过；`--force` 时删除后重建 |

---

## 路径配置

- **Skills 源目录**：默认 `<cwd>/skills/`，可通过 `HIVEFLOW_SKILLS_DIR` 环境变量覆盖
- **安装目标目录**：默认 `~/.agents/skills/`，可通过 `HIVEFLOW_SKILLS_TARGET_DIR` 环境变量覆盖
- 运行 `hiveflow skills install` 须在项目根目录执行（或设置 `HIVEFLOW_SKILLS_DIR`）

---

## application/skills.py 接口

```python
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TARGET_DIR = Path.home() / ".agents" / "skills"

@dataclass
class SkillInfo:
    name: str
    source: Path       # 项目内 skills/<name>
    target: Path       # ~/.agents/skills/<name>
    installed: bool        # target 存在且为软链接
    linked_correctly: bool # 软链接指向正确的 source

def get_skills_dir() -> Path:
    """优先 HIVEFLOW_SKILLS_DIR 环境变量，否则 cwd/skills/"""

def get_target_dir() -> Path:
    """优先 HIVEFLOW_SKILLS_TARGET_DIR 环境变量，否则 ~/.agents/skills/"""

def list_skills(skills_dir, target_dir) -> list[SkillInfo]: ...

def install_skills(name, skills_dir, target_dir, force) -> list[tuple[str, str]]:
    """返回 [(skill_name, status_message)] 列表"""
```

---

## 测试策略

`tests/test_skills.py` 用 `tmp_path` 构造 skills/ 和 target/ 目录，不操作真实 `~/.agents/skills/`：

- `test_list_skills_not_installed`：skill 存在但 target 不存在 → installed=False
- `test_list_skills_installed`：target 是正确软链接 → installed=True
- `test_install_creates_symlink`：安装后 target 是指向正确 source 的软链接
- `test_install_skips_already_installed`：重复安装不报错
- `test_install_force_replaces_real_directory`：--force 时替换真实目录为软链接
- `test_install_warns_on_wrong_symlink`：软链接指向别处时返回警告消息

---

## 迁移步骤（一次性）

1. 把 `~/.agents/skills/hiveflow-*` 内容复制到项目 `skills/` 目录
2. 删除 `~/.agents/skills/hiveflow-*` 原目录（真实目录）
3. 运行 `hiveflow skills install` 重建软链接

---

## 不在本次范围

- `hiveflow skills uninstall` — backlog
- 多 target 配置文件 — backlog（目前用 env var 即可）
- Skills 自动测试/验证 — backlog
