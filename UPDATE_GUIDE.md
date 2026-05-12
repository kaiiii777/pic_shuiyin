# 在线更新发布说明

软件内置更新地址：

`https://api.github.com/repos/kaiiii777/pic_shuiyin/releases/latest`

## 发布新版

1. 修改 `watermark_tool.py` 顶部的 `APP_VERSION`，例如从 `1.0.0` 改成 `1.0.1`。
2. 重新打包生成 `图片水印工具.exe`。
3. 在 GitHub 仓库 `kaiiii777/pic_shuiyin` 创建一个新的 Release。
4. Release 的 tag 使用版本号，例如 `v1.0.1`。
5. 上传打包好的 `图片水印工具.exe` 到 Release 资源里。
6. 用户点击软件里的“检查更新”，如果远端 tag 版本高于本地 `APP_VERSION`，就会提示下载并自动替换。

## 私有仓库说明

GitHub 私有仓库的 Release 资源默认需要登录凭证，普通 exe 不能安全地内置 GitHub token。

如果仓库保持 private，建议把 `图片水印工具.exe` 放到公开可下载的位置，例如：

- GitHub 的公开 Release 仓库
- 阿里云 OSS
- 腾讯云 COS
- 自己的 HTTPS 服务器

当前代码按公开 GitHub Release 配置。如果需要改成 OSS/COS，只需要调整 `watermark_tool.py` 里的 `UPDATE_API_URL` 和更新解析逻辑。
