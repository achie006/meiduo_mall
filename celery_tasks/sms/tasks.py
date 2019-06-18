from celery_tasks.main import celery_app
from .yuntongxun.sms import CCP


@celery_app.task(name='send_sms_code')   # 只有用此装饰器装饰过的函数才是celery函数
def send_sms_code(mobile, sms_code):
    CCP().send_template_sms(mobile, [sms_code, 5], 1)


# send_sms_code(mobile, sms_code)