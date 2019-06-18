
from django.conf import settings
from django.core.mail import send_mail

from celery_tasks.main import celery_app


@celery_app.task(name='send_verify_email')
def send_email_verify(to_email, verify_url):
    subject = "美多商城邮箱验证"   # 邮件主题
    html_message = '<p>尊敬的用户您好！</p>' \
                   '<p>感谢您使用美多商城。</p>' \
                   '<p>您的邮箱为:%s。请点击此连接激活您的邮箱：</p>' \
                   '<p><a href="%s">%s<a></p>' % (to_email, verify_url, verify_url)
    # send_mail(subject='邮箱主题', message='普通邮件正文', from_email='发件人', recipient_list='收件人列表', html_message='超文件邮件内容')
    send_mail(subject=subject, message='', from_email=settings.EMAIL_FROM, recipient_list=[to_email], html_message=html_message)