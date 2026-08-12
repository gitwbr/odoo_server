import gzip
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKUP_SET_LIMIT = 3


def _remove_file(path):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def _validate_database_dump(backup_file):
    check_file = f'{backup_file}.check'
    try:
        with gzip.open(backup_file, 'rb') as source, open(check_file, 'wb') as target:
            shutil.copyfileobj(source, target)
        subprocess.run(
            ['pg_restore', '--list', check_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
    finally:
        _remove_file(check_file)


def _validate_filestore_archive(archive_file, db_name):
    result = subprocess.run(
        ['tar', '-tzf', archive_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    prefix = f'{db_name}/'
    entries = [line for line in result.stdout.splitlines() if line]
    if not entries or not all(
        entry == db_name or entry.startswith(prefix) for entry in entries
    ):
        raise ValueError('filestore archive contains an unexpected path')


def _complete_backup_sets(backup_dir, db_name):
    backup_dir = Path(backup_dir)
    backup_sets = []
    for dump_file in backup_dir.glob(f'{db_name}_*.dump.gz'):
        suffix = dump_file.name[len(db_name):-len('.dump.gz')]
        filestore_file = backup_dir / f'filestore_{db_name}{suffix}.tar.gz'
        if filestore_file.is_file():
            backup_sets.append((suffix, dump_file, filestore_file))
    return sorted(backup_sets)


def _prune_backup_sets(backup_dir, db_name, keep=BACKUP_SET_LIMIT):
    backup_dir = Path(backup_dir)
    backup_sets = _complete_backup_sets(backup_dir, db_name)
    for _, dump_file, filestore_file in backup_sets[:-keep]:
        dump_file.unlink()
        filestore_file.unlink()
        logger.info(f'已删除旧备份组: {dump_file.name}, {filestore_file.name}')

    kept_sets = backup_sets[-keep:]
    if len(kept_sets) < keep:
        return

    complete_dumps = {dump_file for _, dump_file, _ in backup_sets}
    oldest_kept_suffix = kept_sets[0][0]
    for dump_file in backup_dir.glob(f'{db_name}_*.dump.gz'):
        suffix = dump_file.name[len(db_name):-len('.dump.gz')]
        if dump_file not in complete_dumps and suffix < oldest_kept_suffix:
            dump_file.unlink()
            logger.info(f'已删除过期的数据库单独备份: {dump_file.name}')


def backup_database(instance_id: int, db_name: str, backup_dir: str, backup_name: str = None) -> bool:
    """Create and validate a database/filestore backup set for one tenant."""
    backup_file = None
    compressed_backup_file = None
    filestore_file = None
    try:
        Path(backup_dir).mkdir(parents=True, exist_ok=True)

        if not backup_name:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f'{db_name}_{timestamp}'

        backup_file = os.path.join(backup_dir, f'{backup_name}.dump')
        compressed_backup_file = f'{backup_file}.gz'
        filestore_file = os.path.join(
            backup_dir, f'filestore_{backup_name}.tar.gz'
        )

        db_container = f'client{instance_id}-db{instance_id}-1'
        web_container = f'client{instance_id}-web{instance_id}-1'
        db_user = f'odoo{instance_id}'

        with open(backup_file, 'wb') as output:
            subprocess.run([
                'docker', 'exec', db_container,
                'pg_dump', '-U', db_user, db_name,
                '-Fc', '--clean', '--create',
                f'--role={db_user}', '--verbose',
                '--blobs', '--no-tablespaces',
                '--section=pre-data',
                '--section=data',
                '--section=post-data',
            ], stdout=output, stderr=subprocess.PIPE, check=True)

        subprocess.run(['gzip', backup_file], check=True)

        data_dir = f'/var/lib/odoo/client{instance_id}'
        with open(filestore_file, 'wb') as output:
            subprocess.run([
                'docker', 'exec', web_container,
                'tar', '-C', f'{data_dir}/filestore', '-czf', '-', db_name,
            ], stdout=output, stderr=subprocess.PIPE, check=True)

        _validate_database_dump(compressed_backup_file)
        _validate_filestore_archive(filestore_file, db_name)
        _prune_backup_sets(backup_dir, db_name)

        logger.info(
            f'完整备份组成功: {compressed_backup_file}, {filestore_file}'
        )
        return True

    except subprocess.CalledProcessError as error:
        stderr = error.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors='replace')
        logger.error(f'租户完整备份失败: {stderr or str(error)}')
    except Exception as error:
        logger.error(f'备份过程出错: {str(error)}')

    for path in (backup_file, compressed_backup_file, filestore_file):
        if path:
            _remove_file(path)
    return False


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='备份 Odoo 数据库及 filestore')
    parser.add_argument('instance_id', type=int, help='实例ID')
    parser.add_argument('db_name', type=str, help='数据库名称')
    parser.add_argument('backup_dir', type=str, help='备份目录路径')
    parser.add_argument('--backup-name', help='备份文件名（可选）')
    args = parser.parse_args()

    success = backup_database(
        args.instance_id,
        args.db_name,
        args.backup_dir,
        args.backup_name,
    )
    raise SystemExit(0 if success else 1)
