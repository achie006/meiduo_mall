from jinja2 import Environment
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse


def jinja2_environment(**options):
    env = Environment(**options)
    env.globals.update({
        'static': staticfiles_storage.url,   # 查找静态文件路径
        'url': reverse,                      # 解析路径
    })
    return env


"""
确保可以使用模板引擎中的{{ url('') }} {{ static('') }}这类语句 
"""