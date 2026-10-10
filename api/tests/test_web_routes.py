"""Every page the navigation links to must exist in the repository.

A `.gitignore` rule once swallowed web/app/(app)/data/, so the Data link
shipped as a 404 while the build and every API test stayed green."""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


def nav_links() -> list[str]:
    source = (WEB / "components" / "Nav.tsx").read_text(encoding="utf-8")
    return re.findall(r'href:\s*"(/[a-z]*)"', source)


def test_every_nav_link_has_a_page_file():
    links = nav_links()
    assert "/" in links and "/data" in links and len(links) >= 7
    missing = []
    for href in links:
        page = WEB / "app" / "(app)" / (href.strip("/")) / "page.tsx" if href != "/" else WEB / "app" / "(app)" / "page.tsx"
        if not page.exists():
            missing.append(href)
    assert not missing, f"nav links without a page: {missing}"


def test_page_files_are_not_git_ignored():
    import subprocess
    pages = [str(p.relative_to(WEB.parent)) for p in (WEB / "app").rglob("page.tsx")]
    result = subprocess.run(["git", "check-ignore", *pages], cwd=WEB.parent, capture_output=True, text=True)
    assert result.stdout.strip() == "", f"ignored by git: {result.stdout.strip()}"


def test_every_public_asset_the_app_references_exists_and_is_not_ignored():
    """The sign-in page loads /brand/... before login; a missing file is a broken logo."""
    import re
    import subprocess

    referenced: set[str] = set()
    for path in list((WEB / "app").rglob("*.ts*")) + list((WEB / "components").rglob("*.tsx")):
        referenced |= set(re.findall(r'["\'`](/(?:brand|icons)/[A-Za-z0-9._-]+)["\'`]', path.read_text(encoding="utf-8")))
    assert {"/brand/lifey-logo.webp", "/brand/lifey-mark.webp", "/icons/icon-192.png"} <= referenced
    files = []
    for url in sorted(referenced):
        file = WEB / "public" / url.lstrip("/")
        assert file.exists(), f"{url} is referenced but web/public{url} does not exist"
        files.append(str(file.relative_to(WEB.parent)))
    ignored = subprocess.run(["git", "check-ignore", *files], cwd=WEB.parent, capture_output=True, text=True).stdout
    assert ignored.strip() == "", f"ignored by git: {ignored.strip()}"
    for icon in ("icon.png", "apple-icon.png", "favicon.ico"):
        assert (WEB / "app" / icon).exists(), f"web/app/{icon} missing"


def test_the_web_image_ships_the_public_folder():
    """Next's standalone output leaves public/ out; without this COPY the logo is a 404 in production."""
    dockerfile = (WEB / "Dockerfile").read_text(encoding="utf-8")
    assert "/app/public" in dockerfile and (WEB / "public").is_dir()
