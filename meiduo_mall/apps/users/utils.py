import re

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
# from django.contrib.auth.models import User

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData
# from .models import User
from .models import User


def get_use_by_account(account):
    """根据手机号或者用户名获取user"""
    # get获取为空是会报错
    try:
        if re.match(r'^1[3-9]\d{9}$', account):
            user = User.objects.get(mobile=account)
        else:
            user = User.objects.get(username=account)
    except User.DoesNotExist:
        return None
    return user


class UsernameMobileAuthBackend(ModelBackend):
    """自定义认证后端"""

    def authenticate(self, request, username=None, password=None, **kwargs):
        # 1.获取数据
        user = get_use_by_account(username)

        # 2.校验密码是否正确
        if user and user.check_password(password) and user.is_active:
            # 3.返回user
            return user


def generate_email_verify_url(user):
    """生成邮件的激活连接"""
    serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
    data = {'user_id': user.id, 'email': user.email}
    token = serializer.dumps(data).decode()
    verify_url = settings.EMAIL_VERIFY_URL + '?token=' + token
    return verify_url


def check_verify_token(token):
    """对token进行解密并获取user"""
    serializer = Serializer(settings.SECRET_KEY,3600 * 24)
    try:
        data = serializer.loads(token)
    except BadData:
        return None
    else:
        user_id = data.get('user_id')
        email = data.get('email')
        try:
            user = User.objects.get(id=user_id, email=email)
        except User.DoesNotExist:
            return None
        else:
            return user
