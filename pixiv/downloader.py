"""
下载管理器 - 处理小说下载与缓存
"""

import os
import json
import traceback
import re
from pathlib import Path
from .api import PixivAPI
from .utils import (
    get_default_download_dir, 
    create_directory_if_not_exists, 
    format_novel_title,
    print_progress,
    random_sleep,
    sanitize_filename,
    logger
)

class NovelDownloader:
    """处理Pixiv小说下载与缓存"""
    
    def __init__(self, api=None, download_dir=None, cache_dir=None):
        """
        初始化NovelDownloader类
        
        Args:
            api: PixivAPI实例，如果未提供则创建新实例
            download_dir: 下载目录，默认为用户下载目录下的PixivNovels文件夹
            cache_dir: 缓存目录，默认为下载目录下的.cache文件夹
        """
        self.api = api or PixivAPI()
        self.download_dir = Path(download_dir) if download_dir else get_default_download_dir()
        self.cache_dir = Path(cache_dir) if cache_dir else self.download_dir / ".cache"
        
        # 创建必要的目录
        create_directory_if_not_exists(self.download_dir)
        create_directory_if_not_exists(self.cache_dir)
        
        if logger:
            logger.info(f"NovelDownloader初始化完成，下载目录：{self.download_dir}")
    
    def download_novel(self, novel_id, overwrite=False):
        """
        下载指定ID的小说
        
        Args:
            novel_id: 小说ID
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            str: 小说保存路径
        """
        if logger:
            logger.info(f"开始下载小说: ID={novel_id}")
        
        try:
            # 获取小说详情
            novel_details = self.api.get_novel_detail(novel_id)
            if logger:
                logger.debug(f"小说详情获取成功: ID={novel_id}, 标题={novel_details.get('title', '未知标题')}")
                logger.debug(f"小说详情: {str(novel_details)[:500]}...")
            
            # 获取小说正文
            novel_text = self.api.get_novel_text(novel_id)
            if logger:
                logger.debug(f"小说正文结构: {str(novel_text)[:500]}...")
            
            text_content = novel_text.get("novel_text", {})
            if isinstance(text_content, dict):
                text_content = text_content.get("text", "")
            elif isinstance(text_content, str):
                pass  # 已经是字符串了
            else:
                if logger:
                    logger.warning(f"小说正文格式异常: {type(text_content)}")
                text_content = str(text_content)
                
            text_length = len(text_content)
            
            if not text_content:
                if logger:
                    logger.warning(f"小说正文为空: ID={novel_id}")
            else:
                if logger:
                    logger.debug(f"小说正文获取成功: ID={novel_id}, 长度={text_length}字符")
            
            # 处理标签
            tags = []
            if "tags" in novel_details:
                tags_data = novel_details["tags"]
                if isinstance(tags_data, list):
                    # 新格式: 列表中直接是标签对象
                    for tag_item in tags_data:
                        if isinstance(tag_item, dict) and "name" in tag_item:
                            tags.append(tag_item)
                elif isinstance(tags_data, dict) and "tags" in tags_data:
                    # 旧格式: {"tags": [...]}
                    for tag_item in tags_data["tags"]:
                        if isinstance(tag_item, dict):
                            if "name" in tag_item:
                                tags.append({"name": tag_item["name"]})
                            elif "tag" in tag_item:
                                tags.append({"name": tag_item["tag"]})
            
            # 使用小说详情和正文创建一个完整的小说对象
            try:
                novel = {
                    "id": novel_id,
                    "title": novel_details.get("title", "未知标题"),
                    "caption": novel_details.get("caption", ""),
                    "author": {
                        "id": novel_details.get("user", {}).get("id", "未知ID"),
                        "name": novel_details.get("user", {}).get("name", "未知作者")
                    },
                    "create_date": novel_details.get("create_date", ""),
                    "tags": tags,  # 直接使用处理好的标签列表
                    "page_count": novel_details.get("page_count", 0),
                    "text_length": novel_details.get("text_length", 0),
                    "series": novel_details.get("series"),
                    "text": text_content,
                    "original_text": novel_text,
                    "details": novel_details
                }
                
                if logger:
                    logger.debug(f"构建的小说对象: {str(novel)[:200]}...")
                
                # 保存小说
                return self._save_novel(novel, overwrite)
                
            except Exception as e:
                if logger:
                    logger.error(f"构建小说对象失败: {str(e)}")
                    logger.debug(f"小说详情: {str(novel_details)}")
                raise
                
        except Exception as e:
            error_msg = f"下载小说失败: ID={novel_id}, 错误={str(e)}"
            if logger:
                logger.error(error_msg)
                logger.debug(f"错误详情: {traceback.format_exc()}")
            raise Exception(error_msg)
    
    def download_user_novels(self, user_id, limit=None, offset=0, overwrite=False):
        """
        下载指定用户的所有小说
        
        Args:
            user_id: 用户ID
            limit: 限制下载数量，None表示下载全部
            offset: 开始偏移量
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            list: 下载的小说保存路径列表
        """
        logger.info(f"开始下载用户小说: 用户ID={user_id}, 偏移量={offset}, 限制={limit if limit is not None else '无限制'}")
        
        all_novels = []
        page_limit = 30
        current_offset = offset
        total_count = 0
        
        # 创建用户专用目录
        user_dir = self.download_dir / f"user_{user_id}"
        create_directory_if_not_exists(user_dir)
        
        # 分页获取所有小说
        while True:
            try:
                # 获取一页小说
                logger.debug(f"获取用户小说列表: 用户ID={user_id}, 偏移量={current_offset}, 页大小={page_limit}")
                response = self.api.get_user_novels(user_id, limit=page_limit, offset=current_offset)
                novels = response.get("novels", [])
                
                if not novels:
                    logger.info(f"未找到更多小说，已获取 {len(all_novels)} 篇")
                    break
                    
                # 更新总数
                if total_count == 0 and "total" in response:
                    total_count = response["total"]
                    if limit is not None and limit < total_count:
                        total_count = limit
                    logger.info(f"找到 {total_count} 篇小说")
                
                # 限制下载数量
                if limit is not None:
                    remaining = limit - len(all_novels)
                    if remaining <= 0:
                        logger.info(f"已达到下载限制 {limit}，停止获取更多小说")
                        break
                    if remaining < len(novels):
                        logger.debug(f"剪裁当前页面结果以满足限制: {len(novels)} -> {remaining}")
                        novels = novels[:remaining]
                
                # 添加到列表
                all_novels.extend(novels)
                logger.debug(f"当前已获取 {len(all_novels)} 篇小说")
                
                # 更新偏移量
                current_offset += len(novels)
                
                # 如果这一页小说数量少于page_limit，说明已经到达最后一页
                if len(novels) < page_limit:
                    logger.debug(f"当前页小说数量 ({len(novels)}) 小于页大小 ({page_limit})，已获取所有小说")
                    break
                
                # 随机延迟
                random_sleep()
            except Exception as e:
                logger.error(f"获取用户小说列表失败: 用户ID={user_id}, 偏移量={current_offset}, 错误={str(e)}")
                logger.debug(f"错误详情: {traceback.format_exc()}")
                break
        
        # 下载每一篇小说
        downloaded_paths = []
        failed_count = 0
        
        logger.info(f"开始下载 {len(all_novels)} 篇小说")
        for i, novel in enumerate(all_novels):
            novel_id = novel["id"]
            novel_title = novel.get("title", "未知标题")
            logger.info(f"下载小说 {i+1}/{len(all_novels)}: ID={novel_id}, 标题={novel_title}")
            
            try:
                path = self.download_novel(novel_id, overwrite)
                downloaded_paths.append(path)
                logger.debug(f"小说下载成功: ID={novel_id}, 路径={path}")
            except Exception as e:
                error_msg = f"下载小说失败: ID={novel_id}, 标题={novel_title}, 错误={str(e)}"
                logger.error(error_msg)
                failed_count += 1
            
            # 打印进度
            print_progress(i+1, len(all_novels), prefix="总进度:", suffix="完成")
        
        success_count = len(downloaded_paths)
        logger.info(f"下载完成。成功: {success_count} 篇, 失败: {failed_count} 篇, 总计: {len(all_novels)} 篇")
        return downloaded_paths
    
    def download_bookmarks(self, user_id=None, restrict="public", limit=None, offset=0, tag=None, overwrite=False):
        """
        下载收藏的小说
        
        Args:
            user_id: 用户ID（默认为当前登录用户）
            restrict: 限制类型 ("public" 或 "private")
            limit: 限制下载数量，None表示下载全部
            offset: 开始偏移量
            tag: 过滤标签
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            list: 下载的小说保存路径列表
        """
        user_id = user_id or self.api.auth.user_id
        tag_str = f", 标签={tag}" if tag else ""
        limit_str = f", 限制={limit}" if limit is not None else ", 无限制"
        
        logger.info(f"开始下载收藏小说: 用户ID={user_id}, 类型={restrict}, 偏移量={offset}{tag_str}{limit_str}")
        
        all_bookmarks = []
        page_limit = 30
        current_offset = offset
        total_count = 0
        
        # 创建收藏专用目录
        bookmarks_dir = self.download_dir / f"bookmarks_{restrict}"
        if tag:
            bookmarks_dir = bookmarks_dir / sanitize_filename(tag)
        create_directory_if_not_exists(bookmarks_dir)
        
        # 分页获取所有收藏
        while True:
            try:
                # 获取一页收藏
                logger.debug(f"获取用户收藏: 用户ID={user_id}, 类型={restrict}, 偏移量={current_offset}, 页大小={page_limit}{tag_str}")
                response = self.api.get_user_bookmarks(
                    user_id=user_id, 
                    restrict=restrict, 
                    limit=page_limit, 
                    offset=current_offset,
                    tag=tag
                )
                
                bookmarks = response.get("novels", [])
                
                if not bookmarks:
                    logger.info(f"未找到更多收藏小说，已获取 {len(all_bookmarks)} 篇")
                    break
                    
                # 更新总数
                if total_count == 0 and "total" in response:
                    total_count = response["total"]
                    if limit is not None and limit < total_count:
                        total_count = limit
                    logger.info(f"找到 {total_count} 篇收藏小说")
                
                # 限制下载数量
                if limit is not None:
                    remaining = limit - len(all_bookmarks)
                    if remaining <= 0:
                        logger.info(f"已达到下载限制 {limit}，停止获取更多收藏")
                        break
                    if remaining < len(bookmarks):
                        logger.debug(f"剪裁当前页面结果以满足限制: {len(bookmarks)} -> {remaining}")
                        bookmarks = bookmarks[:remaining]
                
                # 添加到列表
                all_bookmarks.extend(bookmarks)
                logger.debug(f"当前已获取 {len(all_bookmarks)} 篇收藏小说")
                
                # 更新偏移量
                current_offset += len(bookmarks)
                
                # 如果这一页收藏数量少于page_limit，说明已经到达最后一页
                if len(bookmarks) < page_limit:
                    logger.debug(f"当前页收藏数量 ({len(bookmarks)}) 小于页大小 ({page_limit})，已获取所有收藏")
                    break
                
                # 随机延迟
                random_sleep()
            except Exception as e:
                logger.error(f"获取用户收藏失败: 用户ID={user_id}, 类型={restrict}, 偏移量={current_offset}, 错误={str(e)}")
                logger.debug(f"错误详情: {traceback.format_exc()}")
                break
        
        # 下载每一篇小说
        downloaded_paths = []
        failed_count = 0
        
        logger.info(f"开始下载 {len(all_bookmarks)} 篇收藏小说")
        for i, bookmark in enumerate(all_bookmarks):
            novel_id = bookmark["id"]
            novel_title = bookmark.get("title", "未知标题")
            logger.info(f"下载收藏小说 {i+1}/{len(all_bookmarks)}: ID={novel_id}, 标题={novel_title}")
            
            try:
                path = self.download_novel(novel_id, overwrite)
                downloaded_paths.append(path)
                logger.debug(f"收藏小说下载成功: ID={novel_id}, 路径={path}")
            except Exception as e:
                error_msg = f"下载收藏小说失败: ID={novel_id}, 标题={novel_title}, 错误={str(e)}"
                logger.error(error_msg)
                failed_count += 1
            
            # 打印进度
            print_progress(i+1, len(all_bookmarks), prefix="总进度:", suffix="完成")
        
        success_count = len(downloaded_paths)
        logger.info(f"下载完成。成功: {success_count} 篇, 失败: {failed_count} 篇, 总计: {len(all_bookmarks)} 篇")
        return downloaded_paths
    
    def search_and_download(self, keyword, search_target="text", sort="date_desc", limit=None, offset=0, overwrite=False):
        """
        搜索并下载小说
        
        Args:
            keyword: 搜索关键词
            search_target: 搜索目标 ("text", "keyword", "tag")
            sort: 排序方式 ("date_desc", "date_asc", "popular_desc")
            limit: 限制下载数量，None表示下载全部
            offset: 开始偏移量
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            list: 下载的小说保存路径列表
        """
        limit_str = f", 限制={limit}" if limit is not None else ", 无限制"
        logger.info(f"开始搜索并下载小说: 关键词={keyword}, 目标={search_target}, 排序={sort}, 偏移量={offset}{limit_str}")
        
        all_results = []
        page_limit = 30
        current_offset = offset
        total_count = 0
        
        # 创建搜索结果专用目录
        search_dir = self.download_dir / f"search_{search_target}_{sort}" / sanitize_filename(keyword)
        create_directory_if_not_exists(search_dir)
        
        # 分页获取所有搜索结果
        while True:
            try:
                # 获取一页搜索结果
                logger.debug(f"搜索小说: 关键词={keyword}, 目标={search_target}, 排序={sort}, 偏移量={current_offset}, 页大小={page_limit}")
                response = self.api.search_novels(
                    word=keyword,
                    search_target=search_target,
                    sort=sort,
                    limit=page_limit,
                    offset=current_offset
                )
                
                results = response.get("novels", [])
                
                if not results:
                    logger.info(f"未找到更多搜索结果，已获取 {len(all_results)} 篇")
                    break
                    
                # 更新总数
                if total_count == 0 and "total" in response:
                    total_count = response["total"]
                    if limit is not None and limit < total_count:
                        total_count = limit
                    logger.info(f"找到 {total_count} 篇匹配小说")
                
                # 限制下载数量
                if limit is not None:
                    remaining = limit - len(all_results)
                    if remaining <= 0:
                        logger.info(f"已达到下载限制 {limit}，停止获取更多搜索结果")
                        break
                    if remaining < len(results):
                        logger.debug(f"剪裁当前页面结果以满足限制: {len(results)} -> {remaining}")
                        results = results[:remaining]
                
                # 添加到列表
                all_results.extend(results)
                logger.debug(f"当前已获取 {len(all_results)} 篇搜索结果")
                
                # 更新偏移量
                current_offset += len(results)
                
                # 如果这一页结果数量少于page_limit，说明已经到达最后一页
                if len(results) < page_limit:
                    logger.debug(f"当前页搜索结果数量 ({len(results)}) 小于页大小 ({page_limit})，已获取所有结果")
                    break
                
                # 随机延迟
                random_sleep()
            except Exception as e:
                logger.error(f"搜索小说失败: 关键词={keyword}, 目标={search_target}, 排序={sort}, 偏移量={current_offset}, 错误={str(e)}")
                logger.debug(f"错误详情: {traceback.format_exc()}")
                break
        
        # 下载每一篇小说
        downloaded_paths = []
        failed_count = 0
        
        logger.info(f"开始下载 {len(all_results)} 篇搜索结果小说")
        for i, result in enumerate(all_results):
            novel_id = result["id"]
            novel_title = result.get("title", "未知标题")
            logger.info(f"下载搜索结果 {i+1}/{len(all_results)}: ID={novel_id}, 标题={novel_title}")
            
            try:
                path = self.download_novel(novel_id, overwrite)
                downloaded_paths.append(path)
                logger.debug(f"搜索结果下载成功: ID={novel_id}, 路径={path}")
            except Exception as e:
                error_msg = f"下载搜索结果失败: ID={novel_id}, 标题={novel_title}, 错误={str(e)}"
                logger.error(error_msg)
                failed_count += 1
            
            # 打印进度
            print_progress(i+1, len(all_results), prefix="总进度:", suffix="完成")
        
        success_count = len(downloaded_paths)
        logger.info(f"下载完成。成功: {success_count} 篇, 失败: {failed_count} 篇, 总计: {len(all_results)} 篇")
        return downloaded_paths
    
    def _save_novel(self, novel, overwrite=False):
        """
        保存小说到文件
        
        Args:
            novel: 小说对象
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            str: 小说保存路径
        """
        # 格式化小说标题（用于文件名）
        title = format_novel_title(
            novel["title"], 
            novel["author"]["name"], 
            novel["id"]
        )
        
        # 确保文件名安全，处理可能包含的特殊字符
        safe_title = sanitize_filename(title)
        if logger:
            logger.debug(f"原始标题: {title}")
            logger.debug(f"安全文件名: {safe_title}")
        
        # 路径
        json_path = self.cache_dir / f"{novel['id']}.json"
        txt_path = self.download_dir / f"{safe_title}.txt"
        
        # 保存原始JSON数据（用于缓存）
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(novel, f, ensure_ascii=False, indent=2)
            if logger:
                logger.debug(f"已保存小说JSON数据: {json_path}")
        except Exception as e:
            if logger:
                logger.error(f"保存小说JSON数据失败: {str(e)}")
        
        # 如果TXT文件已存在且不覆盖，则跳过
        if txt_path.exists() and not overwrite:
            if logger:
                logger.info(f"小说文件已存在，跳过: {txt_path}")
            return txt_path
        
        # 格式化小说内容
        content = self._format_novel_content(novel)
        
        # 创建目录（如果不存在）
        create_directory_if_not_exists(txt_path.parent)
        
        # 保存TXT文件
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(content)
            if logger:
                logger.info(f"已保存小说TXT文件: {txt_path}")
        except Exception as e:
            if logger:
                logger.error(f"保存小说TXT文件失败: {str(e)}")
            raise
        
        return txt_path
    
    def _format_novel_content(self, novel):
        """
        格式化小说内容为TXT格式
        
        Args:
            novel: 小说对象
            
        Returns:
            str: 格式化后的内容
        """
        # 检查小说内容是否为空
        if not novel["text"]:
            if logger:
                logger.warning(f"小说内容为空: ID={novel['id']}, 标题={novel['title']}")
        
        # 处理标签
        tags = []
        if "tags" in novel and isinstance(novel["tags"], list):
            for tag_item in novel["tags"]:
                if isinstance(tag_item, dict) and "name" in tag_item:
                    tag_name = tag_item["name"]
                    translated = tag_item.get("translated_name")
                    if translated:
                        tags.append(f"{tag_name} ({translated})")
                    else:
                        tags.append(tag_name)
                elif isinstance(tag_item, str):
                    tags.append(tag_item)
        
        # 标题部分
        header = [
            f"标题: {novel['title']}",
            f"作者: {novel['author']['name']}",
            f"ID: {novel['id']}",
            f"创建日期: {novel['create_date']}",
            f"字数: {novel['text_length']}",
            f"标签: {', '.join(tags)}",
            "",
            "=" * 50,
            ""
        ]
        
        # 描述部分
        caption = []
        if novel["caption"]:
            caption = [
                "简介:",
                novel["caption"],
                "",
                "=" * 50,
                ""
            ]
        
        # 正文部分
        text = novel["text"]
        
        # 检查系列信息
        series_info = []
        if novel["series"]:
            try:
                series_title = novel["series"].get("title", "未知系列")
                series_id = novel["series"].get("id", "未知ID")
                series_order = novel["series"].get("order", "未知")
                series_total = novel["series"].get("total", "未知")
                
                series_info = [
                    f"系列: {series_title} (ID: {series_id})",
                ]
                
                # 添加位置信息，如"第3篇，共12篇"
                if series_order and series_total:
                    series_info.append(f"位置: 第{series_order}篇，共{series_total}篇")
                
                # 添加前后作品链接
                prev_novel = novel["series"].get("prev", {})
                next_novel = novel["series"].get("next", {})
                
                if prev_novel and prev_novel.get("id"):
                    prev_id = prev_novel.get("id")
                    prev_title = prev_novel.get("title", "未知标题")
                    series_info.append(f"上一篇: [{prev_id}] {prev_title}")
                
                if next_novel and next_novel.get("id"):
                    next_id = next_novel.get("id")
                    next_title = next_novel.get("title", "未知标题")
                    series_info.append(f"下一篇: [{next_id}] {next_title}")
                
                series_info.extend(["", "=" * 50, ""])
                
                if logger:
                    logger.debug(f"添加系列信息: {series_title} (ID: {series_id}, 位置: {series_order}/{series_total})")
            except Exception as e:
                if logger:
                    logger.error(f"处理系列信息时出错: {str(e)}")
        
        # 合并所有部分
        content = "\n".join(header + series_info + caption + [text])
        
        return content
        
    def download_series(self, series_id, overwrite=False):
        """
        下载系列小说中的所有作品
        
        Args:
            series_id: 系列ID
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            list: 下载的小说文件路径列表
        """
        if logger:
            logger.info(f"开始下载系列小说: 系列ID={series_id}")
            
        try:
            # 获取系列信息
            series_details = self.api.get_series_details(series_id)
            if logger:
                logger.debug(f"系列信息获取成功: ID={series_id}, 标题={series_details.get('title', '未知标题')}")
            
            # 创建系列目录
            series_title = series_details.get("title", "未知系列")
            series_dir = self.download_dir / f"series_{series_id}_{series_title}"
            create_directory_if_not_exists(series_dir)
            if logger:
                logger.info(f"使用系列目录: {series_dir}")
            
            # 获取系列中所有的小说
            novels = self.api.get_series_novels(series_id)
            novel_ids = [novel.get("id") for novel in novels if novel.get("id")]
            
            if not novel_ids:
                if logger:
                    logger.warning(f"系列中未找到小说: ID={series_id}")
                return []
            
            if logger:
                logger.info(f"准备下载系列中的 {len(novel_ids)} 篇小说")
            
            # 保存原下载目录
            original_dir = self.download_dir
            
            try:
                # 临时设置下载目录为系列目录
                self.download_dir = series_dir
                
                # 依次下载每篇小说
                downloaded_paths = []
                for i, novel_id in enumerate(novel_ids):
                    if logger:
                        logger.info(f"下载系列小说 {i+1}/{len(novel_ids)}: ID={novel_id}")
                    
                    try:
                        path = self.download_novel(novel_id, overwrite)
                        downloaded_paths.append(path)
                        if logger:
                            logger.info(f"系列小说下载成功: ID={novel_id}, 路径={path}")
                    except Exception as e:
                        if logger:
                            logger.error(f"下载系列小说失败: ID={novel_id}, 错误={str(e)}")
                    
                    # 打印进度
                    print_progress(i+1, len(novel_ids), prefix="系列进度:", suffix="完成")
                
                # 创建系列索引文件
                index_path = series_dir / f"00_系列索引_{series_title}.txt"
                self._create_series_index(index_path, series_details, novels, downloaded_paths)
                
                if logger:
                    logger.info(f"系列小说下载完成。成功: {len(downloaded_paths)} 篇, 总计: {len(novel_ids)} 篇")
                
                return downloaded_paths
                
            finally:
                # 恢复原下载目录
                self.download_dir = original_dir
                
        except Exception as e:
            error_msg = f"下载系列小说失败: ID={series_id}, 错误={str(e)}"
            if logger:
                logger.error(error_msg)
                logger.debug(f"错误详情: {traceback.format_exc()}")
            raise Exception(error_msg)
    
    def _create_series_index(self, index_path, series_details, novels, downloaded_paths):
        """创建系列索引文件"""
        try:
            # 获取每篇小说的完整信息
            novel_details = {}
            for novel in novels:
                novel_id = novel.get("id", "")
                if novel_id:
                    try:
                        # 获取小说的完整信息
                        details = self.api.get_novel_detail(novel_id)
                        novel_details[novel_id] = details
                        # 添加随机延迟，避免频繁请求
                        random_sleep(0.5, 1.5)
                    except Exception as e:
                        if logger:
                            logger.warning(f"获取小说详情失败: {novel_id}, 错误: {str(e)}")
            
            # 创建索引文件
            with open(index_path, 'w', encoding='utf-8') as f:
                # 系列标题信息
                f.write(f"系列: {series_details.get('title', '未知系列')}\n")
                f.write(f"ID: {series_details.get('id', '未知ID')}\n")
                f.write(f"作者: {series_details.get('user', {}).get('name', '未知作者')}\n")
                f.write(f"作品数: {len(novels)}\n\n")
                
                # 系列描述
                if series_details.get("caption"):
                    f.write("描述:\n")
                    f.write(f"{series_details.get('caption')}\n\n")
                
                # 小说列表
                f.write("=" * 50 + "\n")
                f.write("小说列表:\n")
                f.write("=" * 50 + "\n\n")
                
                for i, novel in enumerate(novels):
                    novel_id = novel.get("id", "")
                    
                    # 从小说详情中获取更多信息
                    detail = novel_details.get(novel_id, {})
                    title = detail.get("title", "未知标题")
                    create_date = detail.get("createDate", detail.get("create_date", "未知创建日期"))
                    update_date = detail.get("updateDate", detail.get("update_date", ""))
                    text_count = detail.get("textCount", detail.get("text_length", 0))
                    xRestrict = detail.get("xRestrict", 0)
                    r18_mark = "[R-18] " if xRestrict == 1 else ""
                    
                    # 格式化日期
                    create_date_str = create_date
                    update_date_str = ""
                    if update_date and update_date != create_date:
                        update_date_str = f", 更新: {update_date}"
                    
                    # 写入小说信息
                    f.write(f"{i+1}. [{novel_id}] {r18_mark}{title}\n")
                    f.write(f"   创建: {create_date_str}{update_date_str}\n")
                    f.write(f"   字数: {text_count}\n")
                    
                    # 检查标签
                    tags = detail.get("tags", [])
                    if tags:
                        tag_str = ""
                        if isinstance(tags, list):
                            tag_str = ", ".join([t if isinstance(t, str) else t.get("name", "") for t in tags if t])
                        elif isinstance(tags, dict) and "tags" in tags:
                            tag_str = ", ".join([t.get("tag", "") for t in tags.get("tags", []) if t.get("tag")])
                        if tag_str:
                            f.write(f"   标签: {tag_str}\n")
                    
                    # 描述摘要
                    desc = detail.get("description", detail.get("caption", ""))
                    if desc:
                        # 清理HTML标签
                        desc = re.sub(r'<.*?>', ' ', desc)
                        # 限制长度
                        if len(desc) > 100:
                            desc = desc[:97] + "..."
                        f.write(f"   简介: {desc}\n")
                    
                    f.write("\n")
                
            if logger:
                logger.info(f"系列索引文件已创建: {index_path}")
                
        except Exception as e:
            if logger:
                logger.error(f"创建系列索引文件失败: {str(e)}")
                logger.debug(f"错误详情: {traceback.format_exc()}") 