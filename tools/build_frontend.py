"""Bundle consecutive stylesheets without reordering the CSS cascade."""
from pathlib import Path
import argparse
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]

def build(output):
    output = Path(output).resolve()
    # Never overwrite a checkout or delete an existing user directory.
    if output.exists():
        raise ValueError('A pasta de saída deve ser nova.')
    output.mkdir(parents=True)
    shutil.copytree(ROOT / 'assets', output / 'assets')
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    pattern = re.compile(r'(?P<run><link\b[^>]*href="\./assets/css/[^\"]+"[^>]*>(?:\s*<link\b[^>]*href="\./assets/css/[^\"]+"[^>]*>)*)')
    index = 0
    def combine(match):
        nonlocal index
        links = re.findall(r'<link\b[^>]+>', match.group())
        groups = []
        for link in links:
            rel = re.search(r'rel="([^"]+)"', link).group(1)
            tool = re.search(r'data-lazy-tool="([^"]+)"', link)
            key = (rel, tool.group(1) if tool else '')
            if not groups or groups[-1][0] != key:
                groups.append((key, []))
            groups[-1][1].append(link)
        result = []
        for (rel, tool), group in groups:
            if len(group) == 1:
                result.extend(group)
                continue
            index += 1
            name = f'compiled-{index}.css'
            parts = []
            for link in group:
                source = re.search(r'href="([^"?]+)',link).group(1).removeprefix('./')
                parts.append(f'/* {source} */\n'+(ROOT / source).read_text(encoding='utf-8-sig'))
            css = '\n'.join(parts)
            import hashlib
            version = hashlib.sha256(css.encode()).hexdigest()[:12]
            (output / 'assets/css' / name).write_text(css,encoding='utf-8')
            lazy = f' data-lazy-tool="{tool}"' if tool else ''
            result.append(f'<link rel="{rel}"{lazy} href="./assets/css/{name}?v={version}">')
        return '\n  '.join(result)
    html = pattern.sub(combine, html)
    (output / 'index.html').write_text(html,encoding='utf-8')
    (output / '.nojekyll').touch()

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    build(parser.parse_args().output)
