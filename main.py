#!/usr/bin/env python3
"""
Pixiv小说下载器 - 主程序入口
"""

import os
import sys
import argparse
import traceback
from pathlib import Path
from dotenv import load_dotenv

# 导入自定义模块
from pixiv.auth import PixivAuth
from pixiv.api import PixivAPI
from pixiv.downloader import NovelDownloader
from pixiv.utils import create_directory_if_not_exists, setup_logging

def create_parser():
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(description="Pixiv小说下载器 - 下载Pixiv小说并转换为TXT格式")
    
    # 公共参数
    parser.add_argument("--token", help="Pixiv的refresh token（也可以通过.env文件设置PIXIV_REFRESH_TOKEN）")
    parser.add_argument("-o", "--output", help="下载目录路径")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("--debug", action="store_true", help="启用调试模式（详细日志输出）")
    parser.add_argument("--log-dir", help="日志保存目录")
    
    # 创建子命令
    subparsers = parser.add_subparsers(dest="command", help="要执行的命令")
    
    # 下载指定ID的小说
    novel_parser = subparsers.add_parser("novel", help="下载指定ID的小说")
    novel_parser.add_argument("novel_id", help="小说ID")
    novel_parser.add_argument("--token", help="Pixiv的refresh token（也可以通过.env文件设置PIXIV_REFRESH_TOKEN）")
    novel_parser.add_argument("-o", "--output", help="下载目录路径")
    novel_parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    novel_parser.add_argument("--debug", action="store_true", help="启用调试模式（详细日志输出）")
    novel_parser.add_argument("--log-dir", help="日志保存目录")
    
    # 下载指定系列的所有小说
    series_parser = subparsers.add_parser("series", help="下载指定系列的所有小说")
    series_parser.add_argument("series_id", help="系列ID")
    series_parser.add_argument("--token", help="Pixiv的refresh token（也可以通过.env文件设置PIXIV_REFRESH_TOKEN）")
    series_parser.add_argument("-o", "--output", help="下载目录路径")
    series_parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    series_parser.add_argument("--debug", action="store_true", help="启用调试模式（详细日志输出）")
    series_parser.add_argument("--log-dir", help="日志保存目录")
    
    # 下载指定用户的小说
    user_parser = subparsers.add_parser("user", help="下载指定用户的所有小说")
    user_parser.add_argument("user_id", help="用户ID")
    user_parser.add_argument("-l", "--limit", type=int, help="限制下载数量")
    user_parser.add_argument("--offset", type=int, default=0, help="开始偏移量")
    user_parser.add_argument("--token", help="Pixiv的refresh token（也可以通过.env文件设置PIXIV_REFRESH_TOKEN）")
    user_parser.add_argument("-o", "--output", help="下载目录路径")
    user_parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    user_parser.add_argument("--debug", action="store_true", help="启用调试模式（详细日志输出）")
    user_parser.add_argument("--log-dir", help="日志保存目录")
    
    # 下载收藏的小说
    bookmarks_parser = subparsers.add_parser("bookmarks", help="下载收藏的小说")
    bookmarks_parser.add_argument("-u", "--user-id", help="用户ID（默认为当前登录用户）")
    bookmarks_parser.add_argument("-r", "--restrict", choices=["public", "private"], default="public", help="限制类型（public或private）")
    bookmarks_parser.add_argument("-t", "--tag", help="过滤标签")
    bookmarks_parser.add_argument("-l", "--limit", type=int, help="限制下载数量")
    bookmarks_parser.add_argument("--offset", type=int, default=0, help="开始偏移量")
    bookmarks_parser.add_argument("--token", help="Pixiv的refresh token（也可以通过.env文件设置PIXIV_REFRESH_TOKEN）")
    bookmarks_parser.add_argument("-o", "--output", help="下载目录路径")
    bookmarks_parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    bookmarks_parser.add_argument("--debug", action="store_true", help="启用调试模式（详细日志输出）")
    bookmarks_parser.add_argument("--log-dir", help="日志保存目录")
    
    # 搜索并下载小说
    search_parser = subparsers.add_parser("search", help="搜索并下载小说")
    search_parser.add_argument("keyword", help="搜索关键词")
    search_parser.add_argument("--target", choices=["text", "keyword", "tag"], default="text", help="搜索目标")
    search_parser.add_argument("--sort", choices=["date_desc", "date_asc", "popular_desc"], default="date_desc", help="排序方式")
    search_parser.add_argument("-l", "--limit", type=int, help="限制下载数量")
    search_parser.add_argument("--offset", type=int, default=0, help="开始偏移量")
    search_parser.add_argument("--token", help="Pixiv的refresh token（也可以通过.env文件设置PIXIV_REFRESH_TOKEN）")
    search_parser.add_argument("-o", "--output", help="下载目录路径")
    search_parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    search_parser.add_argument("--debug", action="store_true", help="启用调试模式（详细日志输出）")
    search_parser.add_argument("--log-dir", help="日志保存目录")
    
    return parser

def main():
    """主函数"""
    # 加载环境变量
    load_dotenv()
    
    # 解析命令行参数
    parser = create_parser()
    args = parser.parse_args()
    
    # 配置日志记录器 - 先初始化全局日志记录器
    log_level = "DEBUG" if args.debug else "INFO"
    # 确保在导入任何其他模块前初始化日志记录器
    logger = setup_logging(log_dir=args.log_dir, log_level=log_level)
    
    # 导入日志记录器，此时已初始化
    from pixiv.utils import logger
    
    # 创建调试目录
    if args.debug:
        debug_dir = Path("debug")
        try:
            if not debug_dir.exists():
                debug_dir.mkdir(parents=True, exist_ok=True)
                logger.debug(f"创建调试目录: {debug_dir}")
        except Exception as e:
            logger.error(f"创建调试目录失败: {str(e)}")
    
    # 版本和启动信息
    logger.info("=======================")
    logger.info("Pixiv小说下载器 v1.1.0")
    logger.info("=======================")
    
    if not args.command:
        parser.print_help()
        return
    
    # 记录执行的命令
    command_str = f"命令: {args.command}"
    if args.command == "novel":
        command_str += f", 小说ID: {args.novel_id}"
    elif args.command == "series":
        command_str += f", 系列ID: {args.series_id}"
    elif args.command == "user":
        command_str += f", 用户ID: {args.user_id}, 偏移量: {args.offset}, 限制: {args.limit or '无限制'}"
    elif args.command == "bookmarks":
        command_str += f", 用户ID: {args.user_id or '当前用户'}, 类型: {args.restrict}, 标签: {args.tag or '全部'}, 偏移量: {args.offset}, 限制: {args.limit or '无限制'}"
    elif args.command == "search":
        command_str += f", 关键词: {args.keyword}, 目标: {args.target}, 排序: {args.sort}, 偏移量: {args.offset}, 限制: {args.limit or '无限制'}"
    
    logger.info(command_str)
    
    try:
        # 初始化认证
        auth = PixivAuth(args.token)
        
        # 设置下载目录
        download_dir = args.output
        if download_dir:
            download_dir = Path(download_dir)
            logger.info(f"使用自定义下载目录: {download_dir}")
        
        # 初始化下载器
        downloader = NovelDownloader(
            api=PixivAPI(auth),
            download_dir=download_dir
        )
        
        # 执行对应的命令
        if args.command == "novel":
            logger.info(f"准备下载小说: ID={args.novel_id}")
            downloader.download_novel(args.novel_id, args.overwrite)
            
        elif args.command == "series":
            logger.info(f"准备下载系列小说: 系列ID={args.series_id}")
            downloader.download_series(args.series_id, args.overwrite)
            
        elif args.command == "user":
            logger.info(f"准备下载用户小说: 用户ID={args.user_id}")
            downloader.download_user_novels(
                args.user_id,
                limit=args.limit,
                offset=args.offset,
                overwrite=args.overwrite
            )
            
        elif args.command == "bookmarks":
            user_str = args.user_id or "当前登录用户"
            logger.info(f"准备下载收藏小说: 用户={user_str}, 类型={args.restrict}")
            downloader.download_bookmarks(
                user_id=args.user_id,
                restrict=args.restrict,
                tag=args.tag,
                limit=args.limit,
                offset=args.offset,
                overwrite=args.overwrite
            )
            
        elif args.command == "search":
            logger.info(f"准备搜索并下载小说: 关键词={args.keyword}, 目标={args.target}, 排序={args.sort}")
            downloader.search_and_download(
                args.keyword,
                search_target=args.target,
                sort=args.sort,
                limit=args.limit,
                offset=args.offset,
                overwrite=args.overwrite
            )
        
        logger.info("程序执行完成")
            
    except KeyboardInterrupt:
        logger.warning("\n程序已被用户中断")
        sys.exit(1)
    except Exception as e:
        error_msg = f"程序执行出错: {str(e)}"
        logger.error(error_msg)
        logger.debug(f"错误详情:\n{traceback.format_exc()}")
        print(f"错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 