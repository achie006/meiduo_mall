from fdfs_client.client import Fdfs_client

# 创建fdfs客户端
client = Fdfs_client('./client.conf')
# 使用客户端上传图片
ret = client.upload_by_filename('/home/python/Desktop/01.jpeg')
print(ret)