"""Tests for hiveflow skills list/install functionality."""
from pathlib import Path
from hiveflow.application.skills import list_skills, install_skills


def _make_skills_dir(tmp_path: Path) -> Path:
    """Create a fake skills/ directory with two skills."""
    skills_dir = tmp_path / "skills"
    (skills_dir / "hiveflow-daily-check").mkdir(parents=True)
    (skills_dir / "hiveflow-daily-check" / "SKILL.md").write_text("# Daily Check")
    (skills_dir / "hiveflow-portfolio-advisor").mkdir(parents=True)
    (skills_dir / "hiveflow-portfolio-advisor" / "SKILL.md").write_text("# Advisor")
    return skills_dir


def test_list_skills_not_installed(tmp_path: Path) -> None:
    """Skill exists in project but target not installed yet."""
    skills_dir = _make_skills_dir(tmp_path)
    target_dir = tmp_path / "agents" / "skills"
    target_dir.mkdir(parents=True)

    result = list_skills(skills_dir=skills_dir, target_dir=target_dir)

    assert len(result) == 2
    names = {s.name for s in result}
    assert names == {"hiveflow-daily-check", "hiveflow-portfolio-advisor"}
    assert all(not s.installed for s in result)
    assert all(not s.linked_correctly for s in result)


def test_list_skills_installed(tmp_path: Path) -> None:
    """Target is a correct symlink -> installed=True, linked_correctly=True."""
    skills_dir = _make_skills_dir(tmp_path)
    target_dir = tmp_path / "agents" / "skills"
    target_dir.mkdir(parents=True)

    source = skills_dir / "hiveflow-daily-check"
    target = target_dir / "hiveflow-daily-check"
    target.symlink_to(source)

    result = list_skills(skills_dir=skills_dir, target_dir=target_dir)
    by_name = {s.name: s for s in result}

    assert by_name["hiveflow-daily-check"].installed is True
    assert by_name["hiveflow-daily-check"].linked_correctly is True
    assert by_name["hiveflow-portfolio-advisor"].installed is False


def test_install_creates_symlink(tmp_path: Path) -> None:
    """install_skills creates a symlink for each skill."""
    skills_dir = _make_skills_dir(tmp_path)
    target_dir = tmp_path / "agents" / "skills"
    target_dir.mkdir(parents=True)

    results = install_skills(skills_dir=skills_dir, target_dir=target_dir)

    assert len(results) == 2
    statuses = {name: msg for name, msg in results}
    assert "installed" in statuses["hiveflow-daily-check"].lower()
    assert (target_dir / "hiveflow-daily-check").is_symlink()
    assert (target_dir / "hiveflow-daily-check").resolve() == (skills_dir / "hiveflow-daily-check").resolve()


def test_install_skips_already_installed(tmp_path: Path) -> None:
    """Calling install twice on a correct symlink is idempotent."""
    skills_dir = _make_skills_dir(tmp_path)
    target_dir = tmp_path / "agents" / "skills"
    target_dir.mkdir(parents=True)

    install_skills(skills_dir=skills_dir, target_dir=target_dir)
    results = install_skills(skills_dir=skills_dir, target_dir=target_dir)

    statuses = {name: msg for name, msg in results}
    assert "already" in statuses["hiveflow-daily-check"].lower() or "skip" in statuses["hiveflow-daily-check"].lower()


def test_install_force_replaces_real_directory(tmp_path: Path) -> None:
    """--force replaces a real (non-symlink) directory with a symlink."""
    skills_dir = _make_skills_dir(tmp_path)
    target_dir = tmp_path / "agents" / "skills"
    target_dir.mkdir(parents=True)

    # Create a real directory at the target location (simulating old ~/.agents/skills/hiveflow-*)
    real_dir = target_dir / "hiveflow-daily-check"
    real_dir.mkdir()
    (real_dir / "OLD.md").write_text("old content")

    results = install_skills(skills_dir=skills_dir, target_dir=target_dir, force=True)
    statuses = {name: msg for name, msg in results}

    assert (target_dir / "hiveflow-daily-check").is_symlink()
    assert "installed" in statuses["hiveflow-daily-check"].lower()


def test_install_warns_on_wrong_symlink(tmp_path: Path) -> None:
    """If target is a symlink pointing elsewhere, warn and skip (no --force)."""
    skills_dir = _make_skills_dir(tmp_path)
    target_dir = tmp_path / "agents" / "skills"
    target_dir.mkdir(parents=True)

    other = tmp_path / "other"
    other.mkdir()
    (target_dir / "hiveflow-daily-check").symlink_to(other)

    results = install_skills(skills_dir=skills_dir, target_dir=target_dir, force=False)
    statuses = {name: msg for name, msg in results}

    # Should warn, not crash, and NOT change the symlink
    assert "warn" in statuses["hiveflow-daily-check"].lower() or "skip" in statuses["hiveflow-daily-check"].lower()
    assert (target_dir / "hiveflow-daily-check").readlink() == other


def test_install_single_skill_by_name(tmp_path: Path) -> None:
    """install_skills with name= only installs that one skill."""
    skills_dir = _make_skills_dir(tmp_path)
    target_dir = tmp_path / "agents" / "skills"
    target_dir.mkdir(parents=True)

    results = install_skills(name="hiveflow-daily-check", skills_dir=skills_dir, target_dir=target_dir)

    assert len(results) == 1
    assert results[0][0] == "hiveflow-daily-check"
    assert (target_dir / "hiveflow-daily-check").is_symlink()
    assert not (target_dir / "hiveflow-portfolio-advisor").exists()
