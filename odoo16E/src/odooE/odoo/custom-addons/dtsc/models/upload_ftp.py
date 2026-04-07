import ftplib
import traceback
import io
import os
from odoo import models, fields, api

class UploadModel(models.Model):
    _name = 'upload.model'
    _description = 'Upload Model'

    def upload_to_ftp(self, file_content, filename, folder):
        # ftp_server = '43.156.27.132'
        # ftp_username = 'ftpuser'
        # ftp_password = 'wbrtest'
        ftp_server = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_server')
        ftp_username = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_user')
        ftp_password = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_password')
        #ftp_port = '8021'
        
        # 本地保存路径
        # local_save_path = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_local_path')
        # local_folder_path = os.path.join(local_save_path, folder)
        # local_file_path = os.path.join(local_folder_path, filename)
        # 本地保存路径

        try: 
        
            # 本地保存路径
            # if not os.path.exists(local_save_path):
                # os.makedirs(local_save_path, exist_ok=True)
                # os.chmod(local_save_path, 0o777)
                
            # if not os.path.exists(local_folder_path):
                # os.makedirs(local_folder_path, exist_ok=True)
                # os.chmod(local_folder_path, 0o777)
                
            # with open(local_file_path, 'wb') as local_file:
                # local_file.write(file_content)
            # print(f'File saved locally at {local_file_path}')
            # 本地保存路径
        
            with ftplib.FTP(ftp_server, ftp_username, ftp_password) as ftp:
                print('Connected to FTP server')
                items = ftp.nlst()
                print("Current directory contains:")
                for item in items:
                    print(item)
                
                # 设置FTP连接的编码为UTF-8
                ftp.encoding = 'utf-8'
                
                current_directory = ftp.pwd()
                print(f"Current FTP directory: {current_directory}")

                target_folder = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_target_folder')
                # 进入或创建文件夹
                ftp.cwd(target_folder)
                try:
                    ftp.cwd(folder)
                except ftplib.error_perm:
                    ftp.mkd(folder)
                    ftp.cwd(folder)

                print(f'Uploading file to {folder}/{filename}')

                # 使用 BytesIO 创建一个文件类对象
                with io.BytesIO(file_content) as fp:
                    ftp.storbinary(f'STOR {filename}', fp)
                #ftp.storbinary(f'STOR {filename}', file_content)

                print('File upload completed')
                return True
        except Exception as e:
            print(f'FTP upload failed: {e}')
            traceback.print_exc()
            return False