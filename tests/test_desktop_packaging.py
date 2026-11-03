import os
import stat
from pathlib import Path
from zipfile import ZipFile

from tools.build_desktop import _zip_tree


def test_portable_zip_keeps_utf8_names_and_symlinks(tmp_path: Path):
    package = tmp_path / '交付包'
    app = package / '示例.app'
    app.mkdir(parents=True)
    executable = app / '启动程序'
    executable.write_text('app', encoding='utf-8')
    executable.chmod(0o755)
    if os.name != 'nt':
        (app / '共享库').symlink_to('启动程序')
    (package / '操作手册.html').write_text('manual', encoding='utf-8')
    archive = tmp_path / '交付包.zip'

    _zip_tree(package, archive)

    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert '交付包/操作手册.html' in names
        assert all(bundle.getinfo(name).flag_bits & 0x800 for name in names if any(ord(c) > 127 for c in name))
        if os.name != 'nt':
            link = bundle.getinfo('交付包/示例.app/共享库')
            assert stat.S_ISLNK(link.external_attr >> 16)
            assert bundle.read(link).decode() == '启动程序'
        binary = bundle.getinfo('交付包/示例.app/启动程序')
        if os.name != 'nt':
            assert (binary.external_attr >> 16) & 0o111
