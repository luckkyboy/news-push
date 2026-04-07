from pathlib import Path
import os
import shutil
import stat
import subprocess


def test_deploy_script_updates_existing_env_with_current_webhook(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)

    source_script = Path(__file__).resolve().parents[1] / "scripts" / "deploy_docker.sh"
    target_script = scripts_dir / "deploy_docker.sh"
    shutil.copyfile(source_script, target_script)
    target_script.chmod(target_script.stat().st_mode | stat.S_IXUSR)

    (repo_root / ".env").write_text(
        "WECOM_WEBHOOK_URL=\nNEWS_IMAGE_BASE_URL=https://old.example.com\nTZ=Asia/Shanghai\n",
        encoding="utf-8",
    )
    (repo_root / ".env.example").write_text("", encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["WECOM_WEBHOOK_URL"] = "https://example.com/new-webhook"

    subprocess.run(
        ["bash", str(target_script)],
        cwd=repo_root,
        env=env,
        check=True,
    )

    env_file = (repo_root / ".env").read_text(encoding="utf-8")
    assert "WECOM_WEBHOOK_URL=https://example.com/new-webhook" in env_file


def test_deploy_script_prepares_writable_state_storage(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)

    source_script = Path(__file__).resolve().parents[1] / "scripts" / "deploy_docker.sh"
    target_script = scripts_dir / "deploy_docker.sh"
    shutil.copyfile(source_script, target_script)
    target_script.chmod(target_script.stat().st_mode | stat.S_IXUSR)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["WECOM_WEBHOOK_URL"] = "https://example.com/new-webhook"

    subprocess.run(
        ["bash", str(target_script)],
        cwd=repo_root,
        env=env,
        check=True,
    )

    data_dir = repo_root / "data"
    state_file = data_dir / "state.db"

    assert data_dir.is_dir() is True
    assert state_file.exists() is True
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o777
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o666
