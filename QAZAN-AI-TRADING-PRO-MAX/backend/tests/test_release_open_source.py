import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.database import init_db
from app.main import app

setup_logging()
init_db()
client = TestClient(app)


FORBIDDEN_SECRET_PATTERNS = [
    re.compile(r"ais-(?:dev|pre)-[a-z0-9-]+\.europe-west\d+\.run\.app", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z_-]{25,}"),
    re.compile(r"sk-[0-9A-Za-z]{25,}"),
    re.compile(r"ghp_[0-9A-Za-z]{25,}"),
    re.compile(r"@google/genai"),
]


def test_open_source_required_files_and_cross_links() -> None:
    required_files = [
        "LICENSE",
        "README.md",
        "README.ar.md",
        "SECURITY.md",
        ".gitignore",
        ".env.example",
        ".dockerignore",
        "requirements.txt",
        "backend/requirements.txt",
        "package.json",
        "Dockerfile.backend",
        "Dockerfile.frontend",
        "docker/nginx.conf",
        "docker-compose.yml",
        ".github/workflows/ci.yml",
        "scripts/start-local.sh",
        "scripts/start-local.bat",
        "scripts/create_project_backup.py",
        "ANDROID_APK_GUIDE.md",
    ]
    for rel in required_files:
        path = PROJECT_ROOT / rel
        assert path.is_file(), f"Missing required open-source release file: {rel}"

    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Permission is hereby granted, free of charge" in license_text

    readme_en = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    readme_ar = (PROJECT_ROOT / "README.ar.md").read_text(encoding="utf-8")
    assert "README.ar.md" in readme_en
    assert "README.md" in readme_ar

    pkg = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "qazan-ai-trading-pro-max"
    assert pkg["license"] == "MIT"
    assert pkg["private"] is False
    assert "@google/genai" not in pkg.get("dependencies", {})
    assert "@google/genai" not in pkg.get("devDependencies", {})


def test_no_exposed_secrets_or_cloud_builder_urls_in_source() -> None:
    scan_roots = [
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "backend" / "app",
        PROJECT_ROOT / "scripts",
    ]
    scan_files = [
        PROJECT_ROOT / "package.json",
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / "server.ts",
        PROJECT_ROOT / "vite.config.ts",
        PROJECT_ROOT / "capacitor.config.ts",
        PROJECT_ROOT / "index.html",
    ]
    for root in scan_roots:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".css", ".sh", ".bat"}:
                scan_files.append(p)

    for file_path in scan_files:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for pat in FORBIDDEN_SECRET_PATTERNS:
            match = pat.search(content)
            assert match is None, f"Forbidden secret/platform token matched in {file_path}: {match.group(0)}"

    gitignore_text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "!.env.example", "node_modules/", "*.keystore", "*.db", "backups/"):
        assert pattern in gitignore_text


def test_docker_and_ci_configurations_are_well_formed() -> None:
    compose_text = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "Dockerfile.backend" in compose_text
    assert "Dockerfile.frontend" in compose_text
    assert "8001:8001" in compose_text or ":8001" in compose_text
    assert ":3000" in compose_text
    assert "qazan_sqlite_data:" in compose_text

    nginx_text = (PROJECT_ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_pass http://backend:8001/api/;" in nginx_text
    assert 'proxy_set_header Connection "upgrade";' in nginx_text

    ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "npm run lint" in ci_text
    assert "npm run build" in ci_text
    assert "pytest backend/tests" in ci_text
    assert "docker compose config" in ci_text
    assert "assembleDebug" in ci_text


def test_clean_zip_backup_script_excludes_secrets_and_caches() -> None:
    script = PROJECT_ROOT / "scripts" / "create_project_backup.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    meta = json.loads(proc.stdout.strip())
    archive_path = PROJECT_ROOT / meta["path"]
    assert archive_path.is_file()
    assert meta["files_count"] >= 100
    assert meta["size_bytes"] > 500_000

    with zipfile.ZipFile(archive_path, "r") as zf:
        assert zf.testzip() is None
        names = zf.namelist()
        assert any(n.endswith("/LICENSE") for n in names)
        assert any(n.endswith("/README.md") for n in names)
        assert any(n.endswith("/README.ar.md") for n in names)
        for name in names:
            parts = name.split("/")
            assert "node_modules" not in parts
            assert ".git" not in parts
            assert "__pycache__" not in parts
            assert not name.endswith((".env", ".keystore", ".jks", ".db", ".apk", ".aab"))


def test_release_version_and_api_health() -> None:
    settings = get_settings()
    assert settings.APP_VERSION == "1.0.0-open-source"
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["version"] == "1.0.0-open-source"
    assert res.json()["database"]["connected"] is True
