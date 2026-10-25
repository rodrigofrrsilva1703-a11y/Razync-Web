from pathlib import Path
import importlib.util
import re


def test_bundles_preserve_css_order_scripts_and_production_schedule(tmp_path):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('frontend_build',root/'tools/build_frontend.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    target=tmp_path/'site';module.build(target)
    original=(root/'index.html').read_text(encoding='utf-8')
    compiled=(target/'index.html').read_text(encoding='utf-8')
    def links(html):return re.findall(r'<link[^>]+href="(\./assets/css/[^"?]+)',html)
    def styles(base,html):
        chunks=[]
        for name in links(html):
            css=(base/name.removeprefix('./')).read_text(encoding='utf-8-sig')
            for source in links(original):css=css.replace(f'/* {source.removeprefix("./")} */\n','')
            chunks.append(css)
        return ''.join(chunks).replace('\n','').replace('\r','')
    assert styles(root,original)==styles(target,compiled)
    assert re.findall(r'<script[^>]+src="([^"]+)',original)==re.findall(r'<script[^>]+src="([^"]+)',compiled)
    assert (target/'indisponivel.html').read_bytes()==(root/'indisponivel.html').read_bytes()
    assert 'operating-hours.js?' in compiled
    assert (target/'assets/js/operating-hours.js').read_bytes()==(root/'assets/js/operating-hours.js').read_bytes()
    assert len(re.findall(r'<link rel="stylesheet"',compiled))==3

if __name__ == '__main__':
    import tempfile
    with tempfile.TemporaryDirectory(prefix='razync-build-check-') as temporary:
        test_bundles_preserve_css_order_scripts_and_production_schedule(Path(temporary))
    print('Build: cascata CSS, scripts e expediente preservados.')
