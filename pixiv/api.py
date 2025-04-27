"""
Pixiv API封装 - 提供与Pixiv API交互的方法
"""

import requests
import re
import json
from .auth import PixivAuth
from .utils import random_sleep, check_api_response, extract_novel_text_from_html, logger
from pathlib import Path
from datetime import datetime
import traceback
import os
from pixiv.utils import get_default_download_dir

class PixivAPI:
    """Pixiv API封装，提供与Pixiv API交互的方法"""
    
    # Pixiv API端点
    API_BASE = "https://app-api.pixiv.net"
    
    def __init__(self, auth=None):
        """
        初始化PixivAPI类
        
        Args:
            auth: PixivAuth实例，如果未提供则创建新实例
        """
        self.auth = auth or PixivAuth()
        self.auth.ensure_auth()
        if logger:
            logger.info(f"PixivAPI初始化完成，用户ID：{self.auth.user_id}")
    
    def _request(self, method, endpoint, params=None, data=None, headers=None, require_auth=True):
        """
        发送请求到Pixiv API
        
        Args:
            method: 请求方法 (GET, POST等)
            endpoint: API端点
            params: URL参数
            data: 请求数据
            headers: 额外的请求头
            require_auth: 是否需要认证
            
        Returns:
            dict: API响应数据
        """
        url = f"{self.API_BASE}{endpoint}"
        if logger:
            logger.debug(f"API请求: {method} {url}")
        if params and logger:
            logger.debug(f"参数: {params}")
        
        _headers = {}
        if require_auth:
            _headers.update(self.auth.get_auth_headers())
        if headers:
            _headers.update(headers)
        
        response = requests.request(
            method=method,
            url=url,
            params=params,
            data=data,
            headers=_headers
        )
        
        return check_api_response(response, endpoint)
    
    def get_novel_detail(self, novel_id):
        """
        获取小说详情
        
        Args:
            novel_id: 小说ID
            
        Returns:
            dict: 小说详情数据
        """
        if logger:
            logger.info(f"获取小说详情: ID={novel_id}")
        endpoint = f"/v2/novel/detail"
        params = {"novel_id": novel_id}
        response_data = self._request("GET", endpoint, params=params)
        
        # 添加随机延迟
        random_sleep()
        
        # 确保响应中包含novel键
        if isinstance(response_data, dict) and "novel" in response_data:
            return response_data["novel"]
        else:
            error_msg = f"API响应中没有找到novel键: {str(response_data)[:200]}..."
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_novel_text(self, novel_id):
        """
        获取小说正文
        
        Args:
            novel_id: 小说ID
            
        Returns:
            dict: 小说正文数据
        """
        if logger:
            logger.info(f"获取小说正文: ID={novel_id}")
        
        # 清理内容中的[newpage]标记
        def clean_text(text):
            if not text:
                return text
            # 替换[newpage]标记为空行或其他分隔符
            cleaned = re.sub(r'\[newpage\]', '\n\n', text)
            return cleaned
        
        # 判断是否为调试模式
        debug_mode = logger and logger.level <= 10  # DEBUG级别为10
        
        # 设置下载目录中的debug子目录作为保存路径
        debug_dir = None
        if debug_mode:
            download_dir = get_default_download_dir()
            debug_dir = download_dir / "debug"
            
            try:
                if not debug_dir.exists():
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    if logger:
                        logger.debug(f"创建debug目录: {debug_dir}")
            except Exception as e:
                if logger:
                    logger.error(f"创建debug目录失败: {str(e)}")
                debug_mode = False
        
        # 简单直接的保存函数
        def save_content(content, filename, prefix=""):
            if not debug_mode or not debug_dir:
                return False
            
            try:
                path = debug_dir / filename
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                if logger:
                    logger.debug(f"{prefix}内容已保存到: {path}")
                return True
            except Exception as e:
                if logger:
                    logger.error(f"保存失败 {filename}: {str(e)}")
                return False
        
        # 从API结果中提取小说正文
        def extract_from_api_json(json_data):
            novel_text = ""
            try:
                if json_data and not json_data.get("error", True):
                    body = json_data.get("body", {})
                    
                    # 检查是否有content字段
                    if "content" in body:
                        if logger:
                            logger.debug(f"在JSON中找到content字段")
                        novel_text = body["content"]
                    else:
                        # 可能需要从其他位置获取内容
                        if logger:
                            logger.debug(f"JSON中没有content字段，尝试其他方法获取内容")
                        
                        # 保存解析出的内容
                        if debug_mode:
                            save_content(json.dumps(body, ensure_ascii=False, indent=2), 
                                        f"novel_{novel_id}_body.json", "Body JSON")
                    
                    # 记录关键字段
                    if logger and logger.level <= 10:  # 只在DEBUG级别记录
                        for field in ["description", "title", "userName"]:
                            if field in body:
                                logger.debug(f"找到{field}: {body[field]}")
                    
                    # 检查是否有嵌入图片
                    if "textEmbeddedImages" in body and debug_mode:
                        if logger:
                            logger.debug("找到textEmbeddedImages字段")
                        save_content(json.dumps(body["textEmbeddedImages"], ensure_ascii=False, indent=2), 
                                    f"novel_{novel_id}_images.json", "Images JSON")
                
                return novel_text
            except Exception as e:
                if logger:
                    logger.error(f"从API JSON提取内容时出错: {str(e)}")
                return ""
        
        # 标记是否找到内容
        extracted_text = ""
        
        try:
            # 设置标准的浏览器请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': f'https://www.pixiv.net/novel/show.php?id={novel_id}',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
                'Accept': 'application/json'
            }
            # 合并认证头
            headers.update(self.auth.get_auth_headers())
            
            # 直接使用API获取
            api_url = f"https://www.pixiv.net/ajax/novel/{novel_id}"
            if logger:
                logger.debug(f"请求小说API: GET {api_url}")
            
            try:
                api_response = requests.request(
                    method="GET",
                    url=api_url,
                    headers=headers,
                    cookies={'PHPSESSID': self.auth.refresh_token}
                )
                
                api_response.raise_for_status()
                if logger:
                    logger.debug(f"API请求成功，HTTP状态码: {api_response.status_code}")
                
                # 保存原始响应（仅调试模式）
                raw_api_content = api_response.text
                save_content(raw_api_content, f"novel_{novel_id}_api.raw", "API原始")
                
                # 解析JSON
                try:
                    api_result = api_response.json()
                    save_content(json.dumps(api_result, ensure_ascii=False, indent=2), 
                                f"novel_{novel_id}_api.json", "API JSON")
                    
                    # 检查是否有正文内容
                    text_content = extract_from_api_json(api_result)
                    if text_content:
                        if logger:
                            logger.info(f"成功获取小说内容，长度: {len(text_content)} 字符")
                        save_content(text_content, f"novel_{novel_id}_content.txt", "小说内容")
                        extracted_text = text_content
                        return {"novel_text": {"text": clean_text(text_content)}}
                    else:
                        # 尝试获取正文内容的专用API
                        if logger:
                            logger.debug(f"尝试使用内容专用API")
                        content_url = f"https://www.pixiv.net/ajax/novel/{novel_id}/content"
                        try:
                            content_response = requests.request(
                                method="GET",
                                url=content_url,
                                headers=headers,
                                cookies={'PHPSESSID': self.auth.refresh_token}
                            )
                            content_response.raise_for_status()
                            
                            # 保存原始响应（仅调试模式）
                            save_content(content_response.text, f"novel_{novel_id}_content.raw", "内容API原始")
                            
                            # 解析JSON
                            content_result = content_response.json()
                            save_content(json.dumps(content_result, ensure_ascii=False, indent=2), 
                                        f"novel_{novel_id}_content.json", "内容API JSON")
                            
                            if not content_result.get("error", True) and "content" in content_result.get("body", {}):
                                text_content = content_result["body"]["content"]
                                if logger:
                                    logger.info(f"内容API成功获取小说内容，长度: {len(text_content)} 字符")
                                save_content(text_content, f"novel_{novel_id}_content.txt", "内容API内容")
                                extracted_text = text_content
                                return {"novel_text": {"text": clean_text(text_content)}}
                        except Exception as e:
                            if logger:
                                logger.error(f"访问内容API失败: {str(e)}")
                except Exception as e:
                    if logger:
                        logger.error(f"解析API JSON失败: {str(e)}")
            except Exception as e:
                if logger:
                    logger.error(f"API请求失败: {str(e)}")
            
            # 如果有提取的内容但没有返回
            if extracted_text:
                if logger:
                    logger.info(f"使用已提取到的内容，长度: {len(extracted_text)} 字符")
                return {"novel_text": {"text": clean_text(extracted_text)}}
                
            # 如果所有方法都失败了，返回空文本
            if logger:
                logger.warning(f"获取小说内容失败，返回空内容")
            return {"novel_text": {"text": ""}}
                
        except Exception as e:
            if logger:
                logger.error(f"获取小说文本失败: {str(e)}")
                logger.error(traceback.format_exc())
            
            # 如果已经提取到内容，仍然返回
            if extracted_text:
                return {"novel_text": {"text": clean_text(extracted_text)}}
            
            # 返回空文本，避免程序完全崩溃
            return {"novel_text": {"text": ""}}
        finally:
            # 添加随机延迟
            random_sleep()
    
    def get_user_novels(self, user_id, limit=30, offset=0):
        """
        获取用户的小说列表
        
        Args:
            user_id: 用户ID
            limit: 每页数量
            offset: 偏移量（用于分页）
            
        Returns:
            dict: 用户小说列表数据
        """
        if logger:
            logger.info(f"获取用户小说列表: 用户ID={user_id}, 偏移量={offset}, 限制={limit}")
        endpoint = f"/v1/user/novels"
        params = {
            "user_id": user_id,
            "filter": "for_ios",
            "offset": offset,
            "limit": limit
        }
        
        response_data = self._request("GET", endpoint, params=params)
        
        # 记录获取到的小说数量
        novels_count = len(response_data.get("novels", []))
        if logger:
            logger.info(f"获取到 {novels_count} 篇用户小说")
        
        # 添加随机延迟
        random_sleep()
        
        return response_data
    
    def get_user_bookmarks(self, user_id=None, restrict="public", limit=30, offset=0, tag=None):
        """
        获取用户收藏的小说
        
        Args:
            user_id: 用户ID（默认为当前登录用户）
            restrict: 限制类型 ("public" 或 "private")
            limit: 每页数量
            offset: 偏移量（用于分页）
            tag: 过滤的标签
            
        Returns:
            dict: 用户收藏小说数据
        """
        # 如果没有指定用户ID，则使用当前登录用户
        user_id = user_id or self.auth.user_id
        
        tag_info = f", 标签={tag}" if tag else ""
        if logger:
            logger.info(f"获取用户收藏: 用户ID={user_id}, 类型={restrict}, 偏移量={offset}, 限制={limit}{tag_info}")
        
        endpoint = f"/v1/user/bookmarks/novel"
        params = {
            "user_id": user_id,
            "restrict": restrict,
            "filter": "for_ios",
            "offset": offset,
            "limit": limit
        }
        
        if tag:
            params["tag"] = tag
        
        response_data = self._request("GET", endpoint, params=params)
        
        # 记录获取到的收藏数量
        bookmarks_count = len(response_data.get("novels", []))
        if logger:
            logger.info(f"获取到 {bookmarks_count} 篇收藏小说")
        
        # 添加随机延迟
        random_sleep()
        
        return response_data
    
    def search_novels(self, word, search_target="text", sort="date_desc", merge_plain_keyword_results=True, 
                     include_translated_tag_results=True, start_date=None, end_date=None, limit=30, offset=0):
        """
        搜索小说
        
        Args:
            word: 搜索关键词
            search_target: 搜索目标 ("text", "keyword", "tag")
            sort: 排序方式 ("date_desc", "date_asc", "popular_desc")
            merge_plain_keyword_results: 是否合并纯关键字结果
            include_translated_tag_results: 是否包含翻译后的标签结果
            start_date: 开始日期 (格式: "YYYY-MM-DD")
            end_date: 结束日期 (格式: "YYYY-MM-DD")
            limit: 每页数量
            offset: 偏移量（用于分页）
            
        Returns:
            dict: 搜索结果数据
        """
        date_range = ""
        if start_date:
            date_range += f", 开始日期={start_date}"
        if end_date:
            date_range += f", 结束日期={end_date}"
            
        if logger:
            logger.info(f"搜索小说: 关键词={word}, 目标={search_target}, 排序={sort}, 偏移量={offset}, 限制={limit}{date_range}")
        
        endpoint = f"/v1/search/novel"
        
        params = {
            "word": word,
            "search_target": search_target,
            "sort": sort,
            "merge_plain_keyword_results": merge_plain_keyword_results,
            "include_translated_tag_results": include_translated_tag_results,
            "filter": "for_ios",
            "offset": offset,
            "limit": limit
        }
        
        if start_date:
            params["start_date"] = start_date
        
        if end_date:
            params["end_date"] = end_date
        
        response_data = self._request("GET", endpoint, params=params)
        
        # 记录搜索结果数量
        results_count = len(response_data.get("novels", []))
        total_count = response_data.get("total", 0)
        if logger:
            logger.info(f"搜索结果: 当前页 {results_count} 篇, 总计 {total_count} 篇")
        
        # 添加随机延迟
        random_sleep()
        
        return response_data
    
    def get_series_details(self, series_id):
        """
        获取系列详情
        
        Args:
            series_id: 系列ID
            
        Returns:
            dict: 系列详情数据
        """
        if logger:
            logger.info(f"获取系列详情: ID={series_id}")
        
        # 直接使用Web API
        web_url = f"https://www.pixiv.net/ajax/novel/series/{series_id}"
        
        try:
            if logger:
                logger.debug(f"通过Web API获取系列详情: GET {web_url}")
            
            # 设置浏览器标头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
                'Referer': 'https://www.pixiv.net/',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
            }
            
            # 发送请求
            web_response = requests.get(web_url, headers=headers, cookies={'PHPSESSID': self.auth.refresh_token})
            web_response.raise_for_status()
            
            # 解析响应
            web_data = web_response.json()
            
            if web_data and not web_data.get("error", True) and "body" in web_data:
                if logger:
                    logger.info(f"成功获取系列详情: {series_id}")
                
                # 对系列数据进行处理
                series_data = web_data["body"]
                processed_data = {
                    "id": series_data.get("id", series_id),
                    "title": series_data.get("title", "未知系列"),
                    "caption": series_data.get("caption", ""),
                    "create_date": series_data.get("createDate", ""),
                    "content_count": series_data.get("contentCount", 0),
                    "user": {
                        "id": series_data.get("userId", ""),
                        "name": series_data.get("userName", "未知作者")
                    }
                }
                
                # 添加随机延迟
                random_sleep()
                
                return processed_data
            
            error_msg = f"Web API响应中没有找到系列详情: {str(web_data)[:200]}..."
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg)
            
        except Exception as e:
            error_msg = f"获取系列详情失败: {str(e)}"
            if logger:
                logger.error(error_msg)
            raise
            
    def get_series_novels(self, series_id, limit=100, offset=0):
        """
        获取系列中的小说列表
        
        Args:
            series_id: 系列ID
            limit: 每页数量（已不使用）
            offset: 偏移量（用于分页）
            
        Returns:
            list: 系列中的小说列表
        """
        if logger:
            logger.info(f"获取系列小说列表: 系列ID={series_id}, 偏移量={offset}")
            
        # 使用确认有效的端点，仅传递offset和order_by参数
        web_url = f"https://www.pixiv.net/ajax/novel/series_content/{series_id}"
        
        params = {
            "offset": offset,
            "order_by": "asc"  # 按顺序排列
        }
        
        try:
            if logger:
                logger.debug(f"获取系列小说列表: GET {web_url}?offset={offset}&order_by=asc")
                
            # 设置浏览器标头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': f'https://www.pixiv.net/novel/series/{series_id}',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
                'Accept': 'application/json'
            }
            
            # 发送请求
            cookies = {'PHPSESSID': self.auth.refresh_token}
            web_response = requests.get(web_url, params=params, headers=headers, cookies=cookies)
            
            # 调试：保存响应内容
            if logger and logger.level <= 10:  # DEBUG级别
                try:
                    debug_path = Path("debug") / f"series_{series_id}_response.json"
                    with open(debug_path, "w", encoding="utf-8") as f:
                        f.write(web_response.text)
                    logger.debug(f"保存系列响应内容到: {debug_path}")
                except Exception as e:
                    logger.error(f"保存响应内容失败: {str(e)}")
            
            # 获取响应文本
            response_text = web_response.text
            if logger:
                logger.debug(f"响应状态码: {web_response.status_code}")
                logger.debug(f"响应内容前200字符: {response_text[:200]}")
            
            # 解析JSON
            try:
                web_data = web_response.json()
                
                # 检查API响应是否成功
                if not web_data.get("error", True) and "body" in web_data:
                    # 直接从page.seriesContents获取小说列表
                    if "page" in web_data["body"] and "seriesContents" in web_data["body"]["page"]:
                        novels = web_data["body"]["page"]["seriesContents"]
                        if logger:
                            logger.info(f"获取到 {len(novels)} 篇系列小说")
                        
                        # 只提取必要的id字段，创建简单的数据结构
                        processed_novels = []
                        for i, novel in enumerate(novels):
                            novel_id = novel.get("id", "")
                            content_order = novel.get("series", {}).get("contentOrder", i+1)
                            
                            if novel_id:
                                processed_novel = {
                                    "id": novel_id,
                                    "series": {
                                        "id": series_id,
                                        "order": content_order
                                    }
                                }
                                processed_novels.append(processed_novel)
                            else:
                                if logger:
                                    logger.warning(f"跳过没有ID的小说: {novel}")
                        
                        # 按系列顺序排序
                        processed_novels.sort(key=lambda x: x["series"]["order"])
                        
                        if logger:
                            novel_ids = [n["id"] for n in processed_novels]
                            logger.info(f"成功提取 {len(processed_novels)} 篇小说ID: {novel_ids}")
                        
                        return processed_novels
                    else:
                        error_msg = "API响应中未找到预期的page.seriesContents结构"
                        if logger:
                            logger.error(f"{error_msg}, 响应: {str(web_data)[:200]}...")
                        raise Exception(error_msg)
                else:
                    error_msg = f"API响应错误: {web_data.get('message', '未知错误')}"
                    if logger:
                        logger.error(error_msg)
                    raise Exception(error_msg)
                    
            except json.JSONDecodeError:
                error_msg = f"解析JSON失败: {response_text[:200]}..."
                if logger:
                    logger.error(error_msg)
                raise Exception(error_msg)
                    
        except Exception as e:
            error_msg = f"获取系列小说列表失败: {str(e)}"
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg) 