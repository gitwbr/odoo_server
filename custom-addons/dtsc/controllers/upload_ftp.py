from odoo import http
from odoo.http import request, Response
from ..models.upload_ftp import UploadModel
import json
import os
import datetime
import io
import fitz  # PyMuPDF
from PIL import Image
import xml.etree.ElementTree as ET
from svglib.svglib import svg2rlg
import logging
import re

_logger = logging.getLogger(__name__)

class UploadController(http.Controller):
    # 定義常量
    TOLERANCE = 0.1  # 允許的誤差範圍（毫米）
    MAX_SIZE_DIFF = 5.0  # 允許的最大尺寸差異（毫米）
    
    def check_image(self, file_content, file_extension, filename):
        try:
            # 如果是AI文件，先檢查是否有未轉換的文本對象
            if file_extension.lower() == '.ai':
                _logger.info('開始檢查AI文件是否存在未轉換的文本對象')
                
                # 檢查未轉換為輪廓的文本對象標記
                text_markers = {
                    'AI文本標記': [
                        rb'%%BeginText',              # AI文本開始
                        rb'%%EndText',                # AI文本結束
                        rb'%%BeginTextObject',        # 文本對象開始
                        rb'%%EndTextObject',          # 文本對象結束
                        rb'<stFnt:fontName>',         # 字體名稱標記
                        rb'<stFnt:fontFamily>',       # 字體族標記
                    ]
                }

                # 檢查是否已轉換為輪廓的標記
                outline_markers = [
                    rb'/TextOutlines\s*true',         # 已轉輪廓標記
                    rb'%%BeginOutline',               # 輪廓開始標記
                    rb'%%EndOutline',                 # 輪廓結束標記
                    rb'/Type\s*/OutlineText',         # 輪廓文本類型
                    rb'/Subtype\s*/Path',             # 路徑類型（通常是輪廓）
                ]

                found_text_objects = {}
                total_count = 0
                has_outlines = False

                # 檢查是否有輪廓標記
                for pattern in outline_markers:
                    try:
                        if re.search(pattern, file_content, re.DOTALL | re.IGNORECASE):
                            has_outlines = True
                            break
                    except Exception as e:
                        _logger.error('輪廓標記檢查錯誤: %s', str(e))

                # 檢查未轉換的文本對象
                for category, patterns in text_markers.items():
                    count = 0
                    for pattern in patterns:
                        try:
                            matches = re.finditer(pattern, file_content, re.DOTALL | re.IGNORECASE)
                            for match in matches:
                                # 檢查這段文本周圍是否有輪廓標記
                                start = max(0, match.start() - 1000)
                                end = min(len(file_content), match.end() + 1000)
                                context = file_content[start:end]
                                
                                # 如果周圍沒有輪廓標記，則計數
                                if not any(re.search(outline, context, re.DOTALL | re.IGNORECASE) 
                                         for outline in outline_markers):
                                    count += 1
                                    _logger.warning('發現未轉換的%s', category)
                        except Exception as e:
                            _logger.error('文本對象檢查錯誤: %s', str(e))
                    if count > 0:
                        found_text_objects[category] = count
                        total_count += count

                if total_count > 0:
                    error_message = "檢測到未轉換為輪廓的文本對象！\n"
                    
                    return {
                        'success': False,
                        'error': error_message
                    }
                else:
                    if not has_outlines:
                        _logger.warning('未檢測到文本對象，建議在Illustrator中確認')

            # 檢查文件名中的尺寸格式
            size_pattern = r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:cm|mm)'

            _logger.info('使用的正則表達式: %s', size_pattern)
            _logger.info('檢查的文件名稱: %s', filename)
            
            match = re.search(size_pattern, filename, re.IGNORECASE)
            
            if not match:
                _logger.warning('檔案名稱 %s 不包含有效的尺寸格式', filename)
                return {
                    'success': False,
                    'error': '檔案名稱必須包含尺寸信息，格式如：100x200cm 或 100x200mm'
                }
            
            # 提取尺寸信息
            width = float(match.group(1))
            height = float(match.group(2))
            # 從完整匹配中提取單位
            full_match = match.group(0).lower()
            unit = 'cm' if 'cm' in full_match else 'mm'
            
            _logger.info('成功匹配尺寸信息：寬度=%s, 高度=%s, 單位=%s', width, height, unit)
            
            # 轉換為毫米
            if unit == 'cm':
                width_mm = width * 10
                height_mm = height * 10
            else:  # 已經是毫米
                width_mm = width
                height_mm = height
                
            _logger.info('檔案名稱中的尺寸: %sx%s%s (轉換為毫米: %sx%smm)', 
                      width, height, unit, width_mm, height_mm)

            def check_dimensions(width_actual, height_actual, width_expected, height_expected):
                """檢查尺寸是否符合要求"""
                # 先乘後除計算等比例高度，並四捨五入到小數點後1位
                height_actual_scaled = round(height_actual * width_expected / width_actual, 1)
                _logger.info('等比例縮放後的高度: %s', height_actual_scaled)
                
                # 將預期高度也四捨五入到小數點後1位
                height_expected_rounded = round(height_expected, 1)
                _logger.info('要求的的高度: %s', height_expected_rounded)
                # 轉換為字符串比較，避免浮點數精度問題
                if str(height_actual_scaled) != str(height_expected_rounded):
                    if height_actual_scaled < height_expected_rounded:
                        return False, "smaller"
                    else:
                        return False, "larger"
                return True, "ok"
            # 創建一個字節流對象
            file_stream = io.BytesIO(file_content)
            _logger.info('開始檢查圖片檔案，檔案擴展名: %s', file_extension)
            
            try:
                # 根據文件類型選擇不同的處理方法
                if file_extension.lower() in ['.ai', '.pdf']:
                    # AI文件和PDF文件使用相同的處理方法
                    _logger.info('處理 AI/PDF 檔案')
                    doc = fitz.open(stream=file_content, filetype="pdf")
                    if doc.page_count > 0:
                        page = doc[0]
                        rect = page.rect
                        width_px = rect.width
                        height_px = rect.height
                        width_mm_actual = rect.width * 0.352778  # 轉換為毫米
                        height_mm_actual = rect.height * 0.352778  # 轉換為毫米
                        doc.close()
                        
                        _logger.info('AI/PDF檔案實際尺寸: %sx%s像素, %sx%s毫米', 
                                  width_px, height_px, width_mm_actual, height_mm_actual)
                        
                        # 檢查尺寸
                        is_valid, reason = check_dimensions(width_mm_actual, height_mm_actual, width_mm, height_mm)
                        if not is_valid:
                            """ if reason == "smaller":
                                return {
                                    'success': False,
                                    'error': f'等比例處理後檔案實際尺寸({width_mm_actual:.2f}x{height_mm_actual:.2f}mm)小於要求尺寸({width_mm:.2f}x{height_mm:.2f}mm)'
                                }
                            else:
                                return {
                                    'success': False,
                                    'error': f'等比例處理後檔案實際尺寸({width_mm_actual:.2f}x{height_mm_actual:.2f}mm)超過要求尺寸({width_mm:.2f}x{height_mm:.2f}mm)5mm以上'
                                } """
                            return {
                                    'success': False,
                                    'error': f'等比例處理後檔案實際尺寸({width_mm_actual:.2f}x{height_mm_actual:.2f}mm)不符合要求尺寸({width_mm:.2f}x{height_mm:.2f}mm)'
                                }
                        
                        return {
                            'success': True,
                            'width_px': width_px,
                            'height_px': height_px,
                            'width_mm': width_mm_actual,
                            'height_mm': height_mm_actual,
                            'filename_size': {
                                'width_mm': width_mm,
                                'height_mm': height_mm
                            }
                        }
                        
                elif file_extension.lower() == '.svg':
                    # SVG文件處理邏輯
                    _logger.info('處理 SVG 檔案')
                    temp_file = '/tmp/temp.svg'
                    with open(temp_file, 'wb') as f:
                        f.write(file_content)
                    
                    tree = ET.parse(temp_file)
                    root = tree.getroot()
                    width = root.get('width')
                    height = root.get('height')
                    
                    if not width or not height:
                        viewbox = root.get('viewBox')
                        if viewbox:
                            _, _, width, height = map(float, viewbox.split())
                    
                    os.remove(temp_file)
                    
                    if width and height:
                        width_px = float(width)
                        height_px = float(height)
                        width_mm_actual = width_px * 25.4 / 96  # 轉換為毫米 (假設96DPI)
                        height_mm_actual = height_px * 25.4 / 96
                        
                        _logger.info('SVG檔案實際尺寸: %sx%s像素, %sx%s毫米', 
                                  width_px, height_px, width_mm_actual, height_mm_actual)
                        
                        # 檢查尺寸
                        is_valid, reason = check_dimensions(width_mm_actual, height_mm_actual, width_mm, height_mm)
                        if not is_valid:
                            if reason == "smaller":
                                return {
                                    'success': False,
                                    'error': f'檔案實際尺寸({width_mm_actual:.2f}x{height_mm_actual:.2f}mm)小於要求尺寸({width_mm:.2f}x{height_mm:.2f}mm)'
                                }
                            else:
                                return {
                                    'success': False,
                                    'error': f'檔案實際尺寸({width_mm_actual:.2f}x{height_mm_actual:.2f}mm)超過要求尺寸({width_mm:.2f}x{height_mm:.2f}mm)5mm以上'
                                }
                        
                        return {
                            'success': True,
                            'width_px': width_px,
                            'height_px': height_px,
                            'width_mm': width_mm_actual,
                            'height_mm': height_mm_actual,
                            'filename_size': {
                                'width_mm': width_mm,
                                'height_mm': height_mm
                            }
                        }
                else:
                    # 其他圖片格式使用PIL處理
                    _logger.info('處理普通圖片檔案')
                    img = Image.open(file_stream)
                    width_px, height_px = img.size
                    width_mm_actual = width_px * 25.4 / 72  # 轉換為毫米 (假設72DPI)
                    height_mm_actual = height_px * 25.4 / 72
                    
                    _logger.info('圖片檔案實際尺寸: %sx%s像素, %sx%s毫米', 
                              width_px, height_px, width_mm_actual, height_mm_actual)
                    
                    # 檢查尺寸
                    is_valid, reason = check_dimensions(width_mm_actual, height_mm_actual, width_mm, height_mm)
                    if not is_valid:
                        if reason == "smaller":
                            return {
                                'success': False,
                                'error': f'檔案實際尺寸({width_mm_actual:.2f}x{height_mm_actual:.2f}mm)小於要求尺寸({width_mm:.2f}x{height_mm:.2f}mm)'
                            }
                        else:
                            return {
                                'success': False,
                                'error': f'檔案實際尺寸({width_mm_actual:.2f}x{height_mm_actual:.2f}mm)超過要求尺寸({width_mm:.2f}x{height_mm:.2f}mm)5mm以上'
                            }
                    
                    return {
                        'success': True,
                        'width_px': width_px,
                        'height_px': height_px,
                        'width_mm': width_mm_actual,
                        'height_mm': height_mm_actual,
                        'filename_size': {
                            'width_mm': width_mm,
                            'height_mm': height_mm
                        }
                    }
            except Exception as e:
                _logger.error('檔案尺寸檢查錯誤: %s', str(e), exc_info=True)
                return {
                    'success': False,
                    'error': str(e)
                }
        except Exception as e:
            _logger.error('檔案尺寸檢查錯誤: %s', str(e), exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/dtsc/upload_file_chunk', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_file_chunk(self):
        _logger.info('開始處理檔案分片上傳')

        file_chunk = request.httprequest.files.get('fileChunk')
        if file_chunk:
            chunk_index = int(request.params.get('chunkIndex'))
            total_chunks = int(request.params.get('totalChunks'))
            user_filename = request.params.get('filename', '')
            file_extension = request.params.get('file_extension', '')
            folder = request.params.get('folder', '其它')
            if user_filename == "false":
                user_filename = ""
            if folder == "false":
                folder = "其它"

            _logger.info('處理第 %s/%s 個分片，檔案名稱: %s, 擴展名: %s, 檔案夾: %s', 
                      chunk_index + 1, total_chunks, user_filename, file_extension, folder)

            temp_folder = "/tmp/odoo/"  # 臨時檔案夾路徑
            if not os.path.exists(temp_folder):
                os.makedirs(temp_folder)
                _logger.info('創建臨時檔案夾: %s', temp_folder)

            # 獲取或創建唯一的文件名
            filename_storage_file = os.path.join(temp_folder, user_filename + "_filename")
            if chunk_index == 0:
                # 對於第一個分片，創建並儲存唯一的文件名
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_filename = f"{user_filename}-{current_time}.{file_extension}"
                with open(filename_storage_file, "w") as f:
                    f.write(new_filename)
                _logger.info('創建新檔案名稱: %s', new_filename)
            else:
                # 讀取儲存的文件名
                with open(filename_storage_file, "r") as f:
                    new_filename = f.read()

            temp_filename = os.path.join(temp_folder, new_filename + ".part" + str(chunk_index))
            final_filename = os.path.join(temp_folder, new_filename)

            with open(temp_filename, "ab") as temp_file:
                temp_file.write(file_chunk.read())
            _logger.info('分片 %s 已保存到臨時檔案: %s', chunk_index + 1, temp_filename)

            if chunk_index == total_chunks - 1:
                _logger.info('所有分片已上傳，開始合併檔案')
                # 重組所有分片為最終文件
                with open(final_filename, "wb") as final_file:
                    for i in range(total_chunks):
                        part_filename = os.path.join(temp_folder, new_filename + ".part" + str(i))
                        with open(part_filename, "rb") as part_file:
                            final_file.write(part_file.read())
                        os.remove(part_filename)
                        _logger.info('已合併並刪除分片檔案: %s', part_filename)

                # 上傳文件到FTP伺服器
                uploader = UploadModel()
                with open(final_filename, 'rb') as file_content:
                    success = uploader.upload_to_ftp(file_content, new_filename, folder)
                os.remove(final_filename)
                _logger.info('檔案上傳到FTP %s: %s', '成功' if success else '失敗', new_filename)

                if success:
                    _logger.info('檔案上傳成功')
                    return Response(json.dumps({'success': True, 'message': 'File uploaded successfully', 'filename': new_filename}), content_type='application/json;charset=utf-8', status=200)
                else:
                    _logger.error('檔案上傳失敗，請檢查FTP連接和權限設置')
                    return Response(json.dumps({
                        'success': False,
                        'message': '檔案上傳失敗，請檢查FTP連接和權限設置'
                    }), content_type='application/json;charset=utf-8', status=500)
            else:
                return Response(json.dumps({'success': True, 'message': 'Chunk uploaded successfully'}), content_type='application/json;charset=utf-8', status=200)
        else:
            _logger.warning('沒有收到檔案分片')
            return Response(json.dumps({'success': False, 'message': 'No file chunk provided'}), content_type='application/json;charset=utf-8', status=400)


    @http.route('/dtsc/upload_file', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_file(self):
        _logger.info('開始處理檔案上傳')
        
        file_content = request.httprequest.files.get('custom_file')
        if file_content:
            # 安全獲取上傳文件的實際文件名
            original_filename = file_content.filename
            _logger.info('收到檔案: %s', original_filename)

            # 提取上傳文件的擴展名
            _, file_extension = os.path.splitext(original_filename)

            # 獲取用戶指定的文件名和檔案夾
            user_filename = request.params.get('filename', '')
            fileName_original = request.params.get('fileName_original', '')
            folder = request.params.get('folder', '其它')
            if user_filename == "false":
                user_filename = ""
            if folder == "false":
                folder = "其它"

            # 獲取當前時間
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 生成新的文件名（包含用戶指定的名稱、當前時間戳和文件的實際後綴）
            #new_filename = f"{user_filename}-{current_time}{file_extension}"
            new_filename = original_filename
            _logger.info('生成新檔案名稱: %s', new_filename)

            # 讀取文件內容
            file_content = file_content.read()
            
            # 檢查文件尺寸
            size_info = self.check_image(file_content, file_extension, fileName_original)
            if not size_info['success']:
                error_msg = size_info.get('error', '未知錯誤')
                _logger.error(error_msg)
                return Response(json.dumps({
                    'success': False,
                    'message': error_msg,
                    'error': error_msg
                }), content_type='application/json;charset=utf-8', status=200)

            _logger.info('檔案尺寸信息: %s', size_info)
            # 暫時返回
            """ return Response(json.dumps({
                'success': True,
                'message': '檔案尺寸檢查通過',
                'size_info': size_info
            }), content_type='application/json;charset=utf-8', status=200) """
            # 執行實際的檔案上傳
            uploader = request.env['upload.model']
            success = uploader.upload_to_ftp(file_content, new_filename, folder)

            if success:
                _logger.info('檔案上傳成功')
                return Response(json.dumps({
                    'success': True,
                    'message': 'File uploaded successfully',
                    'filename': new_filename,
                    'size_info': size_info
                }), content_type='application/json;charset=utf-8', status=200)
            else:
                _logger.error('檔案上傳失敗，請檢查FTP連接和權限設置')
                return Response(json.dumps({
                    'success': False,
                    'message': '檔案上傳失敗，請檢查FTP連接和權限設置',
                    'size_info': size_info
                }), content_type='application/json;charset=utf-8', status=200)
        else:
            _logger.warning('沒有收到檔案')
            return Response(json.dumps({'success': False, 'message': 'No file provided'}), content_type='application/json;charset=utf-8', status=400)

    @http.route('/dtsc/payment_upload_file', type='http', auth='user', methods=['POST'], csrf=False)
    def test_endpoint(self, **kwargs):
        
        print('Upload file method called')
        
        file_content = request.httprequest.files.get('custom_file')
        user_filename = request.params.get('filename', '')
        print(f'user_filename: {user_filename}')
        if file_content:
            # 安全獲取上傳文件的實際文件名
            original_filename = file_content.filename

            # 提取上傳文件的擴展名
            _, file_extension = os.path.splitext(original_filename)

            # 獲取用戶指定的文件名和檔案夾
            user_filename = request.params.get('filename', '')
            #folder = request.params.get('folder', '其它')
            current_user = request.env.user
            folder = current_user.name if current_user else '其它'
        
            if user_filename == "false":
                user_filename = ""
            if folder == "false":
                folder = "其它"

            # 獲取當前時間
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 生成新的文件名（包含用戶指定的名稱、當前時間戳和文件的實際後綴）
            new_filename = f"{user_filename}-{current_time}{file_extension}"

            # 讀取文件內容
            file_content = file_content.read()
            print("File content preview:", file_content[:10])

            print(f'Received file: {new_filename} in folder: {folder}')

            #uploader = UploadModel()
            uploader = request.env['upload.model']
            success = uploader.upload_to_ftp(file_content, new_filename, folder)
            if success:
                print('File uploaded successfully')
                return Response(json.dumps({'success': True, 'message': 'File uploaded successfully', 'filename': new_filename}), content_type='application/json;charset=utf-8', status=200)
            else:
                print('File upload failed——27')
                return Response(json.dumps({'success': False, 'message': 'File upload failed'}), content_type='application/json;charset=utf-8', status=200)
        else:
            return Response(json.dumps({'success': False, 'message': 'No file provided'}), content_type='application/json;charset=utf-8', status=400)