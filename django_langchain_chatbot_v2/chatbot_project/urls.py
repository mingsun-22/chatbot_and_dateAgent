# 本文件为Django项目的全局路由配置文件（chatbot_project/urls.py）
# 其作用是将不同的URL路径分发到对应的视图或子应用（app）中，实现网站的URL管理

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # 管理后台路由：访问 /admin/ 时，转到Django自带的后台管理系统
    path('admin/', admin.site.urls),

    # 主应用路由：将根路径 "" 的请求分发到 chatbot_app 应用的路由配置（chatbot_app/urls.py）
    # 这样所有根路径下的url都会由 chatbot_app 继续分发
    path('', include('chatbot_app.urls')),
]
