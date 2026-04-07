from pathlib import Path
import os
import shutil
import stat
import subprocess


def prepare_script_copy(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)

    source_script = Path(__file__).resolve().parents[1] / "scripts" / "deploy_docker.sh"
    target_script = scripts_dir / "deploy_docker.sh"
    shutil.copyfile(source_script, target_script)
    target_script.chmod(target_script.stat().st_mode | stat.S_IXUSR)
    return repo_root, target_script


def prepare_fake_docker(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)
    return fake_bin


def test_deploy_script_updates_existing_env_with_current_webhook(tmp_path: Path) -> None:
    repo_root, target_script = prepare_script_copy(tmp_path)

    (repo_root / ".env").write_text(
        "WECOM_WEBHOOK_URL=\nNEWS_IMAGE_BASE_URL=https://old.example.com\nTZ=Asia/Shanghai\n",
        encoding="utf-8",
    )
    (repo_root / ".env.example").write_text("", encoding="utf-8")

    fake_bin = prepare_fake_docker(tmp_path)

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
    repo_root, target_script = prepare_script_copy(tmp_path)
    fake_bin = prepare_fake_docker(tmp_path)

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


def test_deploy_script_prunes_unused_images_after_successful_deploy(tmp_path: Path) -> None:
    repo_root, target_script = prepare_script_copy(tmp_path)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{docker_log}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
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

    log_lines = docker_log.read_text(encoding="utf-8").splitlines()

    assert "compose up -d --build" in log_lines
    assert "image prune -f" in log_lines


def test_deploy_script_uses_existing_env_webhook_when_not_passed(tmp_path: Path) -> None:
    repo_root, target_script = prepare_script_copy(tmp_path)
    (repo_root / ".env").write_text(
        "WECOM_WEBHOOK_URL=https://example.com/existing-webhook\nNEWS_IMAGE_BASE_URL=https://old.example.com\nTZ=Asia/Shanghai\n",
        encoding="utf-8",
    )
    fake_bin = prepare_fake_docker(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env.pop("WECOM_WEBHOOK_URL", None)

    subprocess.run(
        ["bash", str(target_script)],
        cwd=repo_root,
        env=env,
        check=True,
    )

    env_file = (repo_root / ".env").read_text(encoding="utf-8")
    assert "WECOM_WEBHOOK_URL=https://example.com/existing-webhook" in env_file


def test_deploy_script_allows_existing_env_without_webhook(tmp_path: Path) -> None:
    repo_root, target_script = prepare_script_copy(tmp_path)
    (repo_root / ".env").write_text(
        "WECOM_WEBHOOK_URL=\nNEWS_IMAGE_BASE_URL=https://old.example.com\nTZ=Asia/Shanghai\n",
        encoding="utf-8",
    )
    fake_bin = prepare_fake_docker(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env.pop("WECOM_WEBHOOK_URL", None)

    subprocess.run(
        ["bash", str(target_script)],
        cwd=repo_root,
        env=env,
        check=True,
    )

    env_file = (repo_root / ".env").read_text(encoding="utf-8")
    assert "WECOM_WEBHOOK_URL=" in env_file


def test_deploy_script_requires_webhook_only_when_env_file_missing(tmp_path: Path) -> None:
    repo_root, target_script = prepare_script_copy(tmp_path)
    fake_bin = prepare_fake_docker(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env.pop("WECOM_WEBHOOK_URL", None)

    result = subprocess.run(
        ["bash", str(target_script)],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "WECOM_WEBHOOK_URL is required when .env does not exist" in result.stdout
