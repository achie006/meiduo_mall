import logging
from random import randint
# from celery_tasks.sms.yuntongxun import CCP
from django import http
from django.views import View
from django_redis import get_redis_connection
from meiduo_mall.utils.response_code import RETCODE
from . import contants
from celery_tasks.sms.tasks import send_sms_code
from meiduo_mall.libs.captcha.captcha import captcha

# Create your views here.

logger = logging.getLogger('django')


class ImageCodeView(View):
    """图形验证码"""

    def get(self, request, uuid):
        # 1.调用SDK方法生成图形验证码
        """

        :param name:表示SDK内部生成的唯一标识
        :param text:表示图形验证码的文字信息
        :param image:图片bytes类型数据
        :return: 返回图片的二进制数据以及规定的图片的类型
        """
        name, text, image = captcha.generate_captcha()
        # 2.将图形验证码的文字存储到redis里
        # 创建redis连接对象
        redis_conn = get_redis_connection('verify_code')  # verify_coed是给数据库起个别名，方便使用
        # setex(key, 过期时间单位秒, 值)
        redis_conn.setex('img_%s' % uuid, 300, text)
        # 3.响应图片内容给前端
        return http.HttpResponse(image, content_type='image/png')


class SMSCodeView(View):
    """短信验证码"""

    def get(self, request, mobile):
        # 连接数据库
        redis_conn = get_redis_connection('verify_code')
        # 尝试这从redis中取出该手机号有没有获取验证码的标签，
        send_flag = redis_conn.get('send_flag_%s' % mobile)
        if send_flag:
            return http.JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '频繁发送验证码'})

        # 提取前端url查询参数传入的image_code, uuid
        image_code_client = request.GET.get('image_code')
        uuid = request.GET.get('uuid')
        # 校验all()
        if all([image_code_client, uuid]) is False:
            return http.HttpResponseForbidden('缺少必要参数')

        # 获取redis中的图形验证码 和前端传入的进行比较
        # 取出redis里面的图形验证码
        image_code_server = redis_conn.get('img_%s' % uuid)

        # 判断redis里的图形验证码是否过期
        if image_code_server is None:
            return http.JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图形验证码已实效'})
        # 删除图形验证码 保证验证码只能使用一次
        redis_conn.delete('img_%s' % uuid)
        # 判断redis数据库中的验证码是否与前端传入的是否一致
        # 判断之前先对redis中取出来的数据进行解码，否则是二进制类型
        # 判断时将图形验证码都转为大写或者小写
        image_code_server = image_code_server.decode()
        if image_code_client.lower() != image_code_server.lower():
            return http.JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图形验证码不正确'})

        # 生成6位随机数 作为短信验证码
        sms_code = '%06d' % randint(0, 999999)
        logger.info(sms_code)
        # 管道技术
        pl = redis_conn.pipeline()
        # 把短信验证码村初到redis中以备后期注册是验证
        # pl.setex('sms_code_%s' % mobile, contants.SMS_CODE_REDIS_EXPIRES, sms_code)
        pl.setex('sms_code_%s' % mobile, 300, sms_code)
        # redis_conn.setex('sms_code_%s' % mobile, contants.SMS_CODE_REDIS_EXPIRES, sms_code)
        # 生成短信验证码以后进行一个标签存储，以备验证频繁发送短信
        pl.setex('send_flag_%s' % mobile, 60, 1)
        # redis_conn.setex('send_flag_%s' % mobile, 60, 1)
        pl.execute()

        # 发短信 通过第三方荣联云通讯
        # CCP().send_template_sms(mobile, [sms_code, contants.SMS_CODE_REDIS_EXPIRES // 60], 1)
        # 使用celery异步处理短信发送
        send_sms_code.delay(mobile, sms_code)
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '发送短信验证码成功'})
