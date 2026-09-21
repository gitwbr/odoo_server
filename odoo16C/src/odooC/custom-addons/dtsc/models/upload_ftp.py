import ftplib
import traceback
import io
import os
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class UploadModel(models.Model):
    _name = 'upload.model'
    _description = 'Upload Model'

    def upload_to_ftp(self, file_content, filename, folder):
        ftp_server = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_server')
        ftp_username = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_user')
        ftp_password = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_password')
        
        _logger.info('FTP連接信息 - 伺服器: %s, 用戶名: %s', ftp_server, ftp_username)
        
        # 本地保存路径
        """ local_save_path = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_local_path')
        local_folder_path = os.path.join(local_save_path, folder)
        local_file_path = os.path.join(local_folder_path, filename)
        
        _logger.info('本地保存路徑: %s', local_file_path) """

        try: 
            # 本地保存路径
            """ if not os.path.exists(local_save_path):
                os.makedirs(local_save_path, exist_ok=True)
                os.chmod(local_save_path, 0o777)
                _logger.info('創建本地保存目錄: %s', local_save_path)
                
            if not os.path.exists(local_folder_path):
                os.makedirs(local_folder_path, exist_ok=True)
                os.chmod(local_folder_path, 0o777)
                _logger.info('創建本地檔案夾: %s', local_folder_path)
                
            with open(local_file_path, 'wb') as local_file:
                local_file.write(file_content)
            _logger.info('檔案已保存到本地: %s', local_file_path) """
        
            with ftplib.FTP(ftp_server, ftp_username, ftp_password) as ftp:
                _logger.info('已連接到FTP伺服器')
                
                # 設置FTP連接的編碼為UTF-8
                ftp.encoding = 'utf-8'
                
                current_directory = ftp.pwd()
                _logger.info('當前FTP目錄: %s', current_directory)

                target_folder = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_target_folder')
                _logger.info('目標FTP目錄: %s', target_folder)
                
                # 進入目標目錄
                ftp.cwd(target_folder)
                try:
                    ftp.cwd(folder)
                    _logger.info('進入檔案夾: %s', folder)
                except ftplib.error_perm:
                    ftp.mkd(folder)
                    ftp.cwd(folder)
                    _logger.info('創建並進入檔案夾: %s', folder)

                _logger.info('開始上傳檔案: %s/%s', folder, filename)

                # 使用 BytesIO 創建一個檔案類對象
                with io.BytesIO(file_content) as fp:
                    ftp.storbinary(f'STOR {filename}', fp)

                _logger.info('檔案上傳完成')
                return True
        except Exception as e:
            _logger.error('FTP上傳失敗: %s', str(e))
            _logger.error('詳細錯誤信息: %s', traceback.format_exc())
            return False