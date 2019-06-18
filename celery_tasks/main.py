from celery import Celery
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "meiduo_mall.settings.dev")
# 1.创建celery实例化对象   创建celery客户端
celery_app = Celery('meiduo')
# 2.加载配置信息  制定谁来当中间人   指定仓库
celery_app.config_from_object('celery_tasks.config')
# 3.自定注册任务（当前celery只处理那些任务）
celery_app.autodiscover_tasks(['celery_tasks.sms', 'celery_tasks.email'])
