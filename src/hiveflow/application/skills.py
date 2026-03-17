"""Skills 管理：列出和安装项目内的 AI Agent skills。"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TARGET_DIR = Path.home() / ".agents" / "skills"


@dataclass
class SkillInfo:
    name: str
    source: Path       # 项目内 skills/<name>
    target: Path       # ~/.agents/skills/<name>
    installed: bool        # target 存在且为软链接指向正确 source
    linked_correctly: bool # 软链接指向正确的 source


def get_skills_dir() -> Path:
    """优先 HIVEFLOW_SKILLS_DIR 环境变量，否则 cwd/skills/。"""
    env = os.environ.get("HIVEFLOW_SKILLS_DIR")
    return Path(env) if env else Path("skills")


def get_target_dir() -> Path:
    """优先 HIVEFLOW_SKILLS_TARGET_DIR 环境变量，否则 ~/.agents/skills/。"""
    env = os.environ.get("HIVEFLOW_SKILLS_TARGET_DIR")
    return Path(env).expanduser() if env else DEFAULT_TARGET_DIR


def list_skills(
    skills_dir: Path | None = None,
    target_dir: Path | None = None,
) -> list[SkillInfo]:
    """列出 skills/ 目录下所有 skill 及其安装状态。"""
    sd = (skills_dir or get_skills_dir()).resolve()
    td = (target_dir or get_target_dir()).resolve()

    if not sd.exists():
        return []

    result = []
    for entry in sorted(sd.iterdir()):
        if not entry.is_dir():
            continue
        target = td / entry.name
        linked_correctly = (
            target.is_symlink() and target.resolve() == entry.resolve()
        )
        installed = target.exists() or target.is_symlink()
        result.append(SkillInfo(
            name=entry.name,
            source=entry,
            target=target,
            installed=installed,
            linked_correctly=linked_correctly,
        ))
    return result


def install_skills(
    name: str | None = None,
    skills_dir: Path | None = None,
    target_dir: Path | None = None,
    force: bool = False,
) -> list[tuple[str, str]]:
    """安装 skills（软链接）。返回 [(skill_name, status_message)] 列表。"""
    sd = (skills_dir or get_skills_dir()).resolve()
    td = (target_dir or get_target_dir()).resolve()
    td.mkdir(parents=True, exist_ok=True)

    skills = list_skills(skills_dir=sd, target_dir=td)
    if name:
        skills = [s for s in skills if s.name == name]

    results = []
    for skill in skills:
        msg = _install_one(skill, force=force)
        results.append((skill.name, msg))
    return results


def _install_one(skill: SkillInfo, force: bool) -> str:
    target = skill.target
    source = skill.source

    if not target.exists() and not target.is_symlink():
        target.symlink_to(source)
        return "installed"

    if target.is_symlink():
        if target.resolve() == source.resolve():
            return "already installed (skipped)"
        # Wrong symlink
        if force:
            target.unlink()
            target.symlink_to(source)
            return "installed (replaced wrong symlink)"
        return f"warning: symlink points elsewhere ({target.readlink()}), skipped (use --force)"

    # Real directory
    if force:
        shutil.rmtree(target)
        target.symlink_to(source)
        return "installed (replaced directory)"
    return "warning: real directory exists, skipped (use --force)"
