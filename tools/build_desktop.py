"""Build an onedir desktop distribution on the native target operating system."""
from __future__ import annotations
import os
import platform
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import sys
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
NAME = '安全设施设计报告工作台'


def _zip_tree(source: Path, archive: Path) -> None:
    """Write a portable UTF-8 ZIP while preserving executable bits and symlinks."""
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as bundle:
        def add(path: Path, name: str) -> None:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, os.readlink(path))
            elif stat.S_ISDIR(mode):
                info = zipfile.ZipInfo(name.rstrip('/') + '/')
                info.create_system = 3
                info.external_attr = (stat.S_IFDIR | (mode & 0o777)) << 16
                bundle.writestr(info, b'')
                for child in sorted(path.iterdir()):
                    add(child, f'{name.rstrip("/")}/{child.name}')
            else:
                bundle.write(path, name)
        add(source, source.name)


def main():
    if sys.platform not in {'darwin', 'win32', 'linux'}:
        raise SystemExit(f'不支持的构建平台：{sys.platform}')
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'generate_icons.py')], cwd=ROOT, check=True)
    icon = ROOT / 'branding' / ({'darwin': 'app-icon.icns', 'win32': 'app-icon.ico', 'linux': 'app-icon.png'}[sys.platform])
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
               '--name', NAME, '--icon', str(icon), '--distpath', str(ROOT / 'dist'),
               '--workpath', str(ROOT / 'build' / 'pyinstaller')]
    for source, dest in [('web','web'),('reference','reference'),('skills','skills'),('branding','branding')]:
        command += ['--add-data', f'{ROOT / source}{os.pathsep}{dest}']
    packages = ['webview','qdrant_client','fastembed','onnxruntime','pypdfium2','PIL']
    if sys.platform == 'linux':
        packages.append('PySide6')
    for package in packages:
        command += ['--collect-all', package]
    command.append(str(ROOT / 'tools' / 'desktop_app.py'))
    subprocess.run(command, cwd=ROOT, check=True)
    dist = ROOT / 'dist'
    app = dist / (NAME + ('.app' if sys.platform == 'darwin' else ''))
    arch = platform.machine().lower().replace('amd64', 'x64').replace('aarch64', 'arm64')
    os_name = {'darwin':'macOS', 'win32':'Windows', 'linux':'Linux'}[sys.platform]
    package_dir = dist / f'交付包-v0.9.0-{os_name}-{arch}'
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)
    shutil.copytree(app, package_dir / app.name, symlinks=True) if app.is_dir() else shutil.copy2(app, package_dir / app.name)
    shutil.copy2(ROOT / '操作手册.html', package_dir / '操作手册.html')
    shutil.copy2(ROOT / 'docs' / '交付与验收' / '桌面版安装与迁移说明.md', package_dir / '安装与迁移说明.md')
    shutil.copy2(ROOT / 'docs' / '交付与验收' / '技术说明.md', package_dir / '技术说明.md')
    shutil.copy2(ROOT / 'docs' / '交付与验收' / '现场演示脚本.md', package_dir / '现场演示脚本.md')
    frozen = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], check=True, capture_output=True, text=True).stdout
    manifest = [
        f'产品：{NAME}', '软件版本：v0.9.0', f'平台：{os_name} {arch}',
        f'构建时间（UTC）：{datetime.now(timezone.utc).isoformat(timespec="seconds")}',
        f'Python：{platform.python_version()}', f'构建系统：{platform.platform()}',
        '构建方式：PyInstaller onedir；必须在目标操作系统原生构建。',
        '依赖版本（构建环境 pip freeze）：', frozen,
    ]
    (package_dir / '构建清单.txt').write_text('\n'.join(manifest), encoding='utf-8')
    if sys.platform == 'darwin':
        archive = dist / f'{NAME}-v0.9.0-{os_name}-{arch}.zip'
        _zip_tree(package_dir, archive)
    elif sys.platform == 'win32':
        archive = Path(str(package_dir) + '.zip')
        _zip_tree(package_dir, archive)
    else:
        archive = dist / (package_dir.name + '.tar.gz')
        with tarfile.open(archive, 'w:gz') as bundle:
            bundle.add(package_dir, arcname=package_dir.name)
    import hashlib
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + '.sha256')
    checksum.write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    print('应用：', app)
    print('交付包：', archive)
    print('SHA-256：', digest)
    print('提示：PyInstaller 必须在各目标操作系统原生环境构建；此构建脚本不生成其他操作系统的二进制。')


if __name__ == '__main__':
    main()
