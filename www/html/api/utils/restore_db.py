import gzip
import logging
import os
import re
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _matching_filestore_file(backup_file, db_name):
    filename = os.path.basename(backup_file)
    match = re.match(
        rf'^{re.escape(db_name)}_(.+)\.dump\.gz$',
        filename,
    )
    if not match:
        raise ValueError('数据库备份文件名格式不正确')
    return os.path.join(
        os.path.dirname(backup_file),
        f'filestore_{db_name}_{match.group(1)}.tar.gz',
    )


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
        raise ValueError('filestore 备份包含异常路径')


def restore_database(
    instance_id: int,
    db_name: str,
    backup_file: str,
    filestore_file: str = None,
) -> bool:
    """Restore a timestamp-matched database and filestore backup set."""
    temp_file = None
    temp_container_file = None
    web_stopped = False
    try:
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f'备份文件不存在: {backup_file}')

        expected_filestore_file = _matching_filestore_file(backup_file, db_name)
        filestore_file = filestore_file or expected_filestore_file
        if os.path.abspath(filestore_file) != os.path.abspath(expected_filestore_file):
            raise ValueError('数据库与 filestore 备份时间戳不匹配')
        if not os.path.exists(filestore_file):
            raise FileNotFoundError(f'filestore 备份文件不存在: {filestore_file}')
        _validate_filestore_archive(filestore_file, db_name)

        db_container = f'client{instance_id}-db{instance_id}-1'
        web_container = f'client{instance_id}-web{instance_id}-1'
        db_user = f'odoo{instance_id}'

        logger.info('停止 Web 容器...')
        subprocess.run(['docker', 'stop', web_container], check=True)
        web_stopped = True

        temp_file = backup_file[:-len('.gz')]
        with gzip.open(backup_file, 'rb') as source, open(temp_file, 'wb') as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)

        temp_container_file = f'/tmp/{os.path.basename(temp_file)}'
        subprocess.run([
            'docker', 'cp', temp_file, f'{db_container}:{temp_container_file}',
        ], check=True)

        logger.info(f'删除现有数据库 {db_name}...')
        subprocess.run([
            'docker', 'exec', db_container,
            'dropdb', '-U', db_user, '--if-exists', db_name,
        ], check=True)

        logger.info(f'创建新数据库 {db_name}...')
        subprocess.run([
            'docker', 'exec', db_container,
            'createdb', '-U', db_user, db_name,
        ], check=True)

        logger.info('开始恢复数据库...')
        subprocess.run([
            'docker', 'exec', db_container,
            'pg_restore', '-U', db_user, '-d', db_name,
            '--no-owner', f'--role={db_user}', temp_container_file,
        ], check=True)

        image_name = subprocess.run(
            ['docker', 'inspect', '--format', '{{.Config.Image}}', web_container],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.strip()
        backup_dir = os.path.abspath(os.path.dirname(filestore_file))
        archive_name = os.path.basename(filestore_file)
        filestore_dir = f'/var/lib/odoo/client{instance_id}/filestore'

        logger.info('开始恢复 filestore...')
        subprocess.run([
            'docker', 'run', '--rm',
            '--volumes-from', web_container,
            '-v', f'{backup_dir}:/backup:ro',
            '--entrypoint', '/bin/bash',
            image_name,
            '-c',
            'set -e; rm -rf -- "$1"; mkdir -p -- "$2"; '
            'tar -xzf "/backup/$3" -C "$2"',
            'restore-filestore',
            f'{filestore_dir}/{db_name}',
            filestore_dir,
            archive_name,
        ], check=True)

        logger.info('数据库及 filestore 恢复成功')
        return True

    except subprocess.CalledProcessError as error:
        logger.error(f'完整恢复失败: {error.stderr or str(error)}')
        return False
    except Exception as error:
        logger.error(f'恢复过程出错: {str(error)}')
        return False
    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
        if temp_container_file:
            subprocess.run([
                'docker', 'exec', db_container,
                'rm', '-f', temp_container_file,
            ], check=False)
        if web_stopped:
            logger.info('重启 Web 容器...')
            subprocess.run(['docker', 'start', web_container], check=True)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='恢复 Odoo 数据库及 filestore')
    parser.add_argument('instance_id', type=int, help='实例ID')
    parser.add_argument('db_name', type=str, help='要恢复的数据库名称')
    parser.add_argument('backup_file', help='数据库备份路径（.dump.gz）')
    parser.add_argument('--filestore-file', help='匹配的 filestore 备份路径')
    args = parser.parse_args()

    success = restore_database(
        args.instance_id,
        args.db_name,
        args.backup_file,
        args.filestore_file,
    )
    raise SystemExit(0 if success else 1)
