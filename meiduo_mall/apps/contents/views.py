import logging

from django.shortcuts import render

# Create your views here.
from django.views import View
from .utils import get_categories

from goods.models import GoodsCategory, GoodsChannel
from .models import ContentCategory, Content

logger = logging.getLogger()


class IndexView(View):
    """展示首页"""

    def get(self, request):
        """
        查询出商品数据类别
            {
               key-组号：value-这一足下的所有一二三级
               '1': {
                        'channels-当前这一组中所有的一级数据': [组1-cat1， 组2-cat2...],
                        'sub_cats': 当前这一组里面的所有二级数据
                        'sub_cats':[{id: cat2.id, name: cat2.name, sub_cats:[cat3, cat3]}, ]
               }
            }
        """


        """
            查询出首页广告数据
            'index_lbt': [lbt1, lbt2...],
            'index_qx': []
        """
        # 定义一个字典用来包装所有广告数据
        contents = {}
        # 获取所有广告类别
        content_category_qs = ContentCategory.objects.all()
        # 遍历广告类别查询集构建广告数据格式
        for cat in content_category_qs:
            contents[cat.key] = cat.content_set.filter(status=True).order_by('sequence')

        context = {
            'categories': get_categories(),
            'contents': contents
        }

        return render(request, 'index.html', context)
