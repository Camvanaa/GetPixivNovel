# Pixiv小说下载器

这个程序可以自动获取Pixiv上的小说并将其转换为TXT格式。

## 功能

- 使用refresh token登录Pixiv账户（支持R18内容）
- 下载指定ID的小说
- 下载指定作者的所有小说
- 下载收藏的小说
- 将小说保存为TXT格式

## 使用方法

1. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

2. 创建`.env`文件，添加你的Pixiv refresh token：
   ```
   PIXIV_REFRESH_TOKEN=你的refresh_token
   ```

3. 运行程序：
   ```
   python main.py
   ```

## 如何获取Pixiv的refresh token

1. 在浏览器中登录Pixiv
2. 打开浏览器开发者工具（F12）
3. 切换到应用/Application选项卡
4. 在左侧找到Cookies，然后选择pixiv.net
5. 查找名为"PHPSESSID"的Cookie
6. 该Cookie值就是refresh token

## 目录结构

```
.
├── main.py              # 主程序入口
├── .env                 # 环境变量（存储refresh token）
├── requirements.txt     # 依赖项列表
└── pixiv/
    ├── __init__.py
    ├── auth.py          # 认证相关功能
    ├── api.py           # Pixiv API接口
    ├── downloader.py    # 下载管理器
    ├── converter.py     # 转换器（HTML到TXT） 
    └── utils.py         # 工具函数
``` 