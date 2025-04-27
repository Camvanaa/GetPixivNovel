"""
工具函数模块 - 提供通用的辅助函数
"""

import os
import re
import time
import random
import json
import logging
import pathlib
import traceback
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from logging.handlers import RotatingFileHandler
from bs4 import BeautifulSoup

# 模拟iOS的User-Agent，参考自Pixiv官方app
USER_AGENT = "PixivIOSApp/7.13.3 (iOS 14.6; iPhone13,2)"

# 配置日志记录器
logger = None

def setup_logging(log_dir=None, log_level="INFO"):
    """设置日志记录器"""
    global logger
    
    if logger is not None:
        return logger
    
    logger = logging.getLogger("PixivNovel")
    
    # 设置日志级别
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    logger.setLevel(numeric_level)
    
    # 创建格式化程序
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 添加控制台处理程序
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 如果指定了日志目录，添加文件处理程序
    if log_dir:
        log_path = Path(log_dir)
        create_directory_if_not_exists(log_path)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_path / f"pixiv_novel_{timestamp}.log"
        
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"日志文件: {log_file}")
    
    return logger

def create_directory_if_not_exists(directory):
    """如果目录不存在，则创建它"""
    try:
        os.makedirs(directory, exist_ok=True)
        if logger:
            logger.debug(f"创建或确认目录存在: {directory}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"创建目录失败 {directory}: {str(e)}")
        return False

def sanitize_filename(filename, replace_char="_"):
    """清理文件名，移除不合法字符"""
    # 替换Windows不允许的文件名字符
    illegal_chars = r'[\\/*?:"<>|]'
    sanitized = re.sub(illegal_chars, replace_char, filename)
    
    # 处理文件名过长的情况
    max_length = 200  # Windows的最大路径长度是260，保守一些
    if len(sanitized) > max_length:
        extension = pathlib.Path(sanitized).suffix
        base_name = sanitized[:-len(extension)] if extension else sanitized
        sanitized = base_name[:max_length-len(extension)] + extension
    
    # 去除前后空格，防止创建文件时出错
    sanitized = sanitized.strip()
    
    # 如果文件名为空，提供默认名称
    if not sanitized:
        sanitized = "unnamed_file"
    
    return sanitized

def random_sleep(min_seconds=1, max_seconds=3):
    """随机休眠一段时间，避免请求过于频繁"""
    sleep_time = random.uniform(min_seconds, max_seconds)
    if logger:
        logger.debug(f"随机休眠 {sleep_time:.2f} 秒")
    time.sleep(sleep_time)

def get_default_download_dir():
    """
    获取默认下载目录
    
    Returns:
        Path: 默认下载目录路径
    """
    download_dir = Path.home() / "Downloads" / "PixivNovels"
    create_directory_if_not_exists(download_dir)
    if logger:
        logger.info(f"默认下载目录: {download_dir}")
    return download_dir

def format_novel_title(novel_info, author_name=None, novel_id=None):
    """
    根据小说信息格式化标题
    
    支持两种格式调用:
    1. format_novel_title(novel_info) - novel_info为dict对象
    2. format_novel_title(title, author_name, novel_id) - 直接传入各个字段
    
    Args:
        novel_info: 小说详情信息或标题字符串
        author_name: 作者名称（可选）
        novel_id: 小说ID（可选）
    
    Returns:
        str: 格式化后的标题，包含ID和标题
    """
    # 检查是否使用第二种调用格式
    if author_name is not None and novel_id is not None:
        # 第二种调用格式，novel_info实际是title
        title = novel_info
        return f"[{novel_id}] {title}"
    
    # 第一种调用格式，从dict获取信息
    if isinstance(novel_info, dict):
        novel_id = novel_info.get('id', 'unknown')
        title = novel_info.get('title', '无标题')
        return f"[{novel_id}] {title}"
    else:
        # 如果不是dict且没有提供其他参数，则简单返回
        return str(novel_info)

def print_progress(current, total, prefix='', suffix='', length=50):
    """
    打印进度条
    
    Args:
        current: 当前进度
        total: 总数
        prefix: 前缀文本
        suffix: 后缀文本
        length: 进度条长度
    """
    percent = int(100 * (current / total))
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end='')
    
    if current == total:
        print()

def check_api_response(response, expected_status=200):
    """检查API响应是否成功并返回JSON数据"""
    if logger:
        logger.debug(f"API响应状态码: {response.status_code}")
    
    # 获取内容类型
    content_type = response.headers.get('Content-Type', '')
    
    # 只有非预期状态码才视为错误
    if response.status_code != expected_status and response.status_code != 200:
        error_msg = f"API请求失败: 状态码={response.status_code}, 响应={response.text[:200]}..."
        if logger:
            logger.error(error_msg)
        raise Exception(error_msg)
    
    # 处理HTML响应
    if 'text/html' in content_type:
        if logger:
            logger.debug("收到HTML响应，尝试从中提取数据")
        html_content = response.text
        
        # 保存HTML以供调试
        if logger and logger.level <= logging.DEBUG:
            try:
                debug_dir = Path("debug")
                create_directory_if_not_exists(debug_dir)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                url_path = urlparse(response.url).path.replace('/', '_')
                html_file = debug_dir / f"response_{timestamp}_{url_path}.html"
                
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.debug(f"已保存HTML响应到: {html_file}")
            except Exception as e:
                if logger:
                    logger.error(f"保存HTML响应失败: {str(e)}")
                
        return html_content
    
    # 处理JSON响应
    if 'application/json' in content_type:
        try:
            return response.json()
        except json.JSONDecodeError as e:
            error_msg = f"解析JSON失败: {str(e)}, 响应={response.text[:200]}..."
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg)
    
    # 如果不是HTML或JSON，则返回原始文本
    if logger:
        logger.warning(f"未知的内容类型: {content_type}，返回原始文本")
    return response.text

def extract_novel_text_from_html(html_content):
    """
    从HTML中提取小说文本内容
    
    Args:
        html_content: 网页HTML内容
        
    Returns:
        dict: 提取的小说正文数据
    """
    if logger:
        logger.debug("开始从HTML中提取小说内容")
    
    try:
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 方法1：查找正文内容区域 - 通常是特定的div或section
        novel_content = soup.select_one('#novel-content')
        if novel_content:
            if logger:
                logger.debug("通过#novel-content选择器找到小说内容")
            return {"text": novel_content.get_text().strip()}
        
        # 方法2：尝试查找包含JS数据的脚本
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.string
            if not script_text:
                continue
                
            # 尝试查找预加载数据
            if 'pixiv.novel.details.novel' in script_text:
                if logger:
                    logger.debug("在脚本中找到小说预加载数据")
                import re
                import json
                
                # 正则表达式匹配预加载JSON数据
                pattern = r'pixiv\.novel\.details\.novel\s*=\s*(\{.*?\});'
                match = re.search(pattern, script_text, re.DOTALL)
                if match:
                    try:
                        novel_data = json.loads(match.group(1))
                        if 'content' in novel_data:
                            if logger:
                                logger.debug(f"从脚本中提取的JSON数据中找到content字段")
                            return {"text": novel_data['content']}
                    except json.JSONDecodeError:
                        if logger:
                            logger.warning("解析脚本中的JSON数据失败")
        
        # 方法3：查找其他可能包含小说内容的元素
        main_content = soup.select_one('main') or soup.select_one('.main-content')
        if main_content:
            if logger:
                logger.debug("通过main或.main-content选择器找到可能的小说内容区域")
            # 排除不相关的元素
            for element in main_content.select('header, footer, nav, .advertisement'):
                element.decompose()
            return {"text": main_content.get_text().strip()}
        
        # 尝试直接从JSON模块中获取内容
        json_script = soup.find("meta", {"id": "meta-preload-data"})
        if json_script and json_script.has_attr("content"):
            try:
                json_data = json.loads(json_script["content"])
                novel_id = None
                
                # 找到小说ID
                for key in json_data.get("novel", {}).keys():
                    if key.isdigit():
                        novel_id = key
                        break
                
                if novel_id and "novel" in json_data and novel_id in json_data["novel"]:
                    novel_data = json_data["novel"][novel_id]
                    if "content" in novel_data:
                        if logger:
                            logger.debug(f"从meta-preload-data中找到小说内容")
                        return {"text": novel_data["content"]}
            except json.JSONDecodeError:
                if logger:
                    logger.warning("解析meta-preload-data中的JSON数据失败")
        
        # 如果以上方法都失败，记录警告并返回空内容
        if logger:
            logger.warning("未能从HTML中提取到小说内容")
        return {"text": ""}
        
    except Exception as e:
        if logger:
            logger.error(f"从HTML提取小说内容时出错: {str(e)}")
            logger.error(traceback.format_exc())
        return {"text": ""} 