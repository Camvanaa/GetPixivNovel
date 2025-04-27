"""
处理Pixiv的身份验证和Token管理
"""

import os
import json
import time
import requests
import traceback
from dotenv import load_dotenv
from .utils import USER_AGENT, logger

# 加载环境变量
load_dotenv()

class PixivAuth:
    """处理Pixiv的身份验证和Token管理"""
    
    # Pixiv API相关常量
    AUTH_TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
    CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
    CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
    
    def __init__(self, refresh_token=None):
        """
        初始化PixivAuth类
        
        Args:
            refresh_token: Pixiv的refresh token，若为None则尝试从环境变量获取
        """
        self.refresh_token = refresh_token or os.getenv("PIXIV_REFRESH_TOKEN")
        if not self.refresh_token:
            error_msg = "未提供refresh token，请在.env文件中设置PIXIV_REFRESH_TOKEN或直接传入refresh_token参数"
            if logger:
                logger.error(error_msg)
            raise ValueError(error_msg)
        
        if logger:
            logger.debug(f"使用refresh token初始化PixivAuth: {self.refresh_token[:5]}...{self.refresh_token[-5:]} (已屏蔽中间部分)")
        
        self.access_token = None
        self.token_expiry_time = 0
        self.user_id = None
        self.headers = self._get_default_headers()
    
    def _get_default_headers(self):
        """获取默认请求头"""
        headers = {
            "User-Agent": USER_AGENT,
            "app-os": "ios",
            "app-os-version": "14.6",
            "Accept-Language": "zh-CN",
            "Accept": "*/*",
            "Connection": "keep-alive"
        }
        if logger:
            logger.debug(f"创建默认请求头: User-Agent={USER_AGENT}")
        return headers
    
    def login(self):
        """
        使用refresh token登录并获取access token
        
        Returns:
            bool: 登录是否成功
        """
        if logger:
            logger.info("开始使用refresh token获取访问令牌")
        data = {
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "get_secure_url": "true",
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        
        try:
            headers = self._get_default_headers()
            headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": "oauth.secure.pixiv.net"
            })
            
            # 使用代理的选项（如果需要）
            proxies = None
            # 检查环境变量是否有代理设置
            http_proxy = os.getenv("HTTP_PROXY")
            https_proxy = os.getenv("HTTPS_PROXY")
            
            if http_proxy or https_proxy:
                proxies = {}
                if http_proxy:
                    proxies["http"] = http_proxy
                    if logger:
                        logger.debug(f"使用HTTP代理: {http_proxy}")
                if https_proxy:
                    proxies["https"] = https_proxy
                    if logger:
                        logger.debug(f"使用HTTPS代理: {https_proxy}")
            
            if logger:
                logger.debug(f"发送认证请求到 {self.AUTH_TOKEN_URL}")
            response = requests.post(
                self.AUTH_TOKEN_URL,
                data=data,
                headers=headers,
                proxies=proxies
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            # 记录token数据（不记录敏感信息）
            if logger:
                logger.debug("成功获取访问令牌数据")
            
            self.access_token = token_data["access_token"]
            if logger:
                logger.debug(f"获取到access_token: {self.access_token[:5]}...{self.access_token[-5:]} (已屏蔽中间部分)")
            
            self.refresh_token = token_data["refresh_token"]  # 更新refresh token
            if logger:
                logger.debug(f"获取到refresh_token: {self.refresh_token[:5]}...{self.refresh_token[-5:]} (已屏蔽中间部分)")
            
            # 设置token过期时间（提前5分钟过期以防超时）
            self.token_expiry_time = time.time() + token_data["expires_in"] - 300
            expires_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.token_expiry_time))
            if logger:
                logger.debug(f"令牌过期时间: {expires_date}")
            
            self.user_id = token_data["user"]["id"]
            
            # 更新请求头
            self.headers.update({"Authorization": f"Bearer {self.access_token}"})
            
            if logger:
                logger.info(f"登录成功，用户ID: {self.user_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            if logger:
                logger.error(f"网络请求失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                if logger:
                    logger.error(f"状态码: {e.response.status_code}")
                try:
                    error_json = e.response.json()
                    if logger:
                        logger.error(f"错误详情: {json.dumps(error_json, ensure_ascii=False)}")
                except:
                    if logger:
                        logger.error(f"响应内容: {e.response.text[:200]}...")
            return False
        except Exception as e:
            if logger:
                logger.error(f"登录过程中发生错误: {str(e)}")
                logger.debug(f"错误详情: {traceback.format_exc()}")
            return False
    
    def ensure_auth(self):
        """
        确保有效的身份验证
        如果token已过期则自动刷新
        
        Returns:
            bool: 是否有有效的身份验证
        """
        current_time = time.time()
        
        # 检查token状态
        if self.access_token is None:
            if logger:
                logger.info("尚未获取访问令牌，尝试登录")
            return self.login()
        elif current_time >= self.token_expiry_time:
            expiry_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.token_expiry_time))
            current_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))
            if logger:
                logger.info(f"访问令牌已过期，尝试刷新。当前时间: {current_time_str}, 过期时间: {expiry_time_str}")
            return self.login()
        
        if logger:
            logger.debug("当前访问令牌有效，无需刷新")
        return True
    
    def get_auth_headers(self):
        """
        获取包含身份验证信息的请求头
        
        Returns:
            dict: 请求头字典
        """
        if not self.ensure_auth():
            error_msg = "无法获取有效的身份验证"
            if logger:
                logger.error(error_msg)
            raise Exception(error_msg)
        return self.headers 