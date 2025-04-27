import os
import re
import json
import time
import requests
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime

from pixiv.utils import (
    USER_AGENT,
    random_sleep,
    sanitize_filename,
    check_api_response,
    extract_novel_text_from_html,
    format_novel_title,
    logger,
    create_directory_if_not_exists
)
from pixiv.api import PixivAPI

class PixivNovelDownloader:
    """Pixiv小说下载器"""
    
    def __init__(self, session=None, output_dir=None, api=None):
        """初始化下载器"""
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Referer': 'https://www.pixiv.net/',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
        })
        
        self.output_dir = Path(output_dir) if output_dir else Path.cwd() / "downloads"
        create_directory_if_not_exists(self.output_dir)
        
        # 添加API实例
        self.api = api or PixivAPI()
        
        # 重试配置
        self.max_retries = 3
        self.retry_delay = 2
        
        if logger:
            logger.info(f"使用输出目录: {self.output_dir}")
    
    def download_novel(self, novel_id, output_format="txt"):
        """
        下载指定ID的小说
        
        Args:
            novel_id: 小说ID
            output_format: 输出格式，支持txt和html
            
        Returns:
            str: 保存的文件路径
        """
        if logger:
            logger.info(f"开始下载小说 ID: {novel_id}")
        
        # 获取小说详情
        novel_info = self.get_novel_info(novel_id)
        
        # 获取小说内容
        novel_content_data = self.get_novel_content(novel_id)
        novel_content = novel_content_data.get("content", "")
        
        if not novel_content:
            error_msg = f"无法获取小说内容: {novel_id}"
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg)
        
        # 格式化标题
        novel_title = format_novel_title(novel_info)
        safe_title = sanitize_filename(novel_title)
        
        # 创建适合的输出路径
        output_path = self.output_dir / f"{safe_title}.{output_format}"
        
        # 保存小说
        if output_format.lower() == "html":
            self._save_as_html(output_path, novel_info, novel_content)
        else:
            self._save_as_txt(output_path, novel_info, novel_content)
        
        if logger:
            logger.info(f"小说已保存到: {output_path}")
        
        return output_path

    def get_novel_info(self, novel_id):
        """获取小说详情信息"""
        if logger:
            logger.debug(f"获取小说详情 ID: {novel_id}")
        
        url = f"https://www.pixiv.net/ajax/novel/{novel_id}"
        
        try:
            response = self.session.get(url)
            data = check_api_response(response)
            
            if isinstance(data, dict) and 'body' in data:
                if logger:
                    logger.debug(f"成功获取小说详情: {novel_id}")
                return data['body']
            else:
                error_msg = f"返回的数据格式不正确: {novel_id}"
                if logger:
                    logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            if logger:
                logger.error(f"获取小说详情失败 {novel_id}: {str(e)}")
            raise
    
    def get_novel_content(self, novel_id):
        """
        获取小说内容
        
        Args:
            novel_id: 小说ID
            
        Returns:
            dict: 包含小说内容和元数据的字典
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                if logger:
                    logger.info(f"获取小说内容 (#{attempt}): ID={novel_id}")
                
                # 使用新的API端点获取小说文本
                api_response = self.api.get_novel_text(novel_id)
                
                if not api_response or not api_response.get("novel_text"):
                    if logger:
                        logger.error(f"获取小说内容失败: 响应为空或没有文本内容")
                    raise Exception("未能获取小说文本内容")
                
                novel_text = api_response.get("novel_text", {})
                text_content = novel_text.get("text", "")
                
                if not text_content:
                    if logger:
                        logger.warning(f"获取到空的小说内容: ID={novel_id}")
                
                return {
                    "content": text_content,
                    "novel_id": novel_id
                }
                
            except Exception as e:
                if logger:
                    logger.error(f"获取小说内容失败 (#{attempt}): {str(e)}")
                
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    if logger:
                        logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    if logger:
                        logger.error(f"超过最大重试次数 ({self.max_retries})，放弃获取小说内容")
                    raise Exception(f"获取小说内容失败: {str(e)}")
    
    def _save_as_txt(self, output_path, novel_info, novel_content):
        """以TXT格式保存小说"""
        try:
            title = novel_info.get('title', '无标题')
            author = novel_info.get('userName', '未知作者')
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"标题: {title}\n")
                f.write(f"作者: {author}\n")
                f.write(f"ID: {novel_info.get('id', 'unknown')}\n")
                f.write(f"发布日期: {novel_info.get('createDate', 'unknown')}\n")
                f.write(f"描述: {novel_info.get('description', '')}\n")
                f.write(f"标签: {', '.join(tag.get('tag', '') for tag in novel_info.get('tags', {}).get('tags', []))}\n")
                f.write("\n" + "="*50 + "\n\n")
                f.write(novel_content)
            
            if logger:
                logger.debug(f"已保存TXT格式小说: {output_path}")
                
        except Exception as e:
            error_msg = f"保存小说为TXT格式失败: {str(e)}"
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg)
    
    def _save_as_html(self, output_path, novel_info, novel_content):
        """以HTML格式保存小说"""
        try:
            title = novel_info.get('title', '无标题')
            author = novel_info.get('userName', '未知作者')
            
            # 添加基本样式的HTML
            html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {author}</title>
    <style>
        body {{
            font-family: 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            margin: 0 auto;
            max-width: 800px;
            padding: 20px;
            color: #333;
            background-color: #f9f9f9;
        }}
        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 10px;
        }}
        .meta {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 0.9em;
        }}
        .tags {{
            margin: 20px 0;
            text-align: center;
        }}
        .tag {{
            display: inline-block;
            background-color: #eee;
            border-radius: 3px;
            padding: 2px 8px;
            margin: 0 5px 5px 0;
            font-size: 0.8em;
            color: #555;
        }}
        .content {{
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: justify;
            white-space: pre-wrap;
        }}
        p {{
            margin-bottom: 1em;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="meta">
        <p>作者: {author}</p>
        <p>发布日期: {novel_info.get('createDate', '未知')}</p>
        <p>ID: {novel_info.get('id', 'unknown')}</p>
    </div>
    <div class="tags">
"""
            
            # 添加标签
            for tag in novel_info.get('tags', {}).get('tags', []):
                html_content += f'        <span class="tag">{tag.get("tag", "")}</span>\n'
            
            html_content += """    </div>
    <div class="content">
"""
            
            # 处理小说内容的换行符
            content_with_paragraphs = novel_content.replace('\n', '</p>\n<p>')
            html_content += f"        <p>{content_with_paragraphs}</p>\n"
            
            html_content += """    </div>
</body>
</html>"""
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            if logger:
                logger.debug(f"已保存HTML格式小说: {output_path}")
                
        except Exception as e:
            error_msg = f"保存小说为HTML格式失败: {str(e)}"
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg)

def main():
    """命令行入口点"""
    parser = argparse.ArgumentParser(description='Pixiv小说下载器')
    parser.add_argument('novel_id', type=str, help='要下载的小说ID')
    parser.add_argument('--format', type=str, choices=['txt', 'html'], default='txt', help='输出格式 (默认: txt)')
    parser.add_argument('--output-dir', type=str, help='输出目录 (默认: ./downloads)')
    
    args = parser.parse_args()
    
    try:
        downloader = PixivNovelDownloader(output_dir=args.output_dir)
        output_path = downloader.download_novel(args.novel_id, args.format)
        print(f"小说已下载到: {output_path}")
        return 0
    except Exception as e:
        if logger:
            logger.error(f"下载失败: {str(e)}")
        else:
            print(f"错误: {str(e)}")
        return 1

if __name__ == "__main__":
    main() 