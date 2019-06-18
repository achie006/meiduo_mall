from django.conf import settings
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData

def generat_openid_signature(openid):
    """对openid进行加密"""
    # 1.创建加密对象
    serializer = Serializer(settings.SECRET_KEY, 600)
    # 2.包装成字典型的数据
    data = {'openid': openid}
    # 3.对数据进行dumps，得到的是bytue数据，需要编译
    openid_sign = serializer.dumps(data)
    return openid_sign.decode()

def check_openid_signature(openid):
    """对openid进行解密"""
    serializer = Serializer(settings.SECRET_KEY, 600)
    try:
        data = serializer.loads(openid)
    except BadData:
        return None
    return data.get('openid')
