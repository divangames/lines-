import tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tarfile.open(root/'private/release.tar.gz','w:gz') as archive:
    for directory in ('dist','server'):
        for path in (root/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.add(path,arcname=path.relative_to(root).as_posix())
    for name in ('requirements.lock.txt','scripts/bootstrap.py'):
        archive.add(root/name,arcname=name)
print('Packaged application; private configuration and credentials excluded')
with tarfile.open(root/'private/source.tar.gz','w:gz') as archive:
    for directory in ('src','server','scripts'):
        for path in (root/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.add(path,arcname=path.relative_to(root).as_posix())
    for name in ('package.json','package-lock.json','index.html','vite.config.js','requirements.txt','requirements.lock.txt',
                 'PRODUCT.md','BRIEF.md','README.md','DESIGN.md','UNSLOP.md','.impeccable/design.json','.gitignore'):
        path=root/name
        if path.is_file(): archive.add(path,arcname=name)
print('Packaged sources and operating instructions; private files excluded')
