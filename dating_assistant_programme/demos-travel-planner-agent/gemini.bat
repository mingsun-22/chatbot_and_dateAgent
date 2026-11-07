@echo off
echo 正在为 Gemini CLI 应用代理: http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890

rem 调用原始的 gemini.cmd，并传递所有参数
gemini.cmd %*