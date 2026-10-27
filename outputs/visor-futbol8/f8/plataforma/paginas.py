"""Main page: loads every file in web/modulos/ in name order, versioned by content hash."""
import hashlib,html
from f8.core.paths import WEB_DIR


def version(path):return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def web_modules(web=WEB_DIR):
    folder=web/'modulos'
    return sorted(folder.glob('*.css')),sorted(folder.glob('*.js'))


def render_index(web=WEB_DIR):
    page=(web/'index.html').read_text(encoding='utf8');styles,scripts=web_modules(web)
    tags=[f'<link rel="stylesheet" href="/modulos/{html.escape(p.name)}?v={version(p)}">' for p in styles]
    tags+=[f'<script defer src="/modulos/{html.escape(p.name)}?v={version(p)}"></script>' for p in scripts]
    page=page.replace('<!--modulos-->',''.join(tags))
    return page.replace('href="/style.css"',f'href="/style.css?v={version(web/"style.css")}"')
