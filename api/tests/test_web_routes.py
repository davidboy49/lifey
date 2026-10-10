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
