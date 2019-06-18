from django import http
from django.shortcuts import render
from django.core.cache import cache
from django.views import View
from meiduo_mall.utils.response_code import RETCODE

from areas.models import Area


class AreasView(View):
    """省市区数据查询"""
    def get(self, request):
        """省市区查询数据"""
        # 接受数据area_id
        area_id = request.GET.get('area_id')
        # 校验area_id是否有值，如果没有值说明要查询所有省
        if area_id is None:
            # 查询所有省数据
            # 先尝试在redis中查询，如果缓存中没有在在mysql中查询
            province_list = cache.get('province_list')
            # 如果在缓存中取不到值则缓存中无数据
            if province_list is None:
                province_qs = Area.objects.filter(parent=None)
                # 把查询集中的对象转换为字典类型
                province_list = []    # 创建一个表用来接受字典数据
                for province_model in province_qs:
                    province_list.append({
                        'id': province_model.id,
                        'name': province_model.name
                    })
                # 获取完省份数据后存入redis缓存，并设置时间
                cache.set('province_list', province_list, 3600)
            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'ok', 'province_list': province_list})
        else:
            # 查询市区的数据
            # 获取指定省或者市的缓存数据
            sub_data = cache.get('sub_area_' + area_id)
            if sub_data is None:
                # 通过area_id来查找单个的省或者市
                try:
                    parent_model = Area.objects.get(id=area_id)
                except Area.DoesNotExist:
                    return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': 'area_id不存在'})
                # 在通过单个省或者市查询出他的下级所有行政区
                subs_qs = parent_model.subs.all()
                # 创建一个列表用来接受所有的市或者区的信息
                sub_list = []
                # 遍历得到的所有行政区，把每个模型转换为字典数据
                for sub_model in subs_qs:
                    sub_list.append({
                        'id': sub_model.id,
                        'name': sub_model.name
                    })
                sub_data = {
                    'id': parent_model.id,
                    'name': parent_model.name,
                    'subs': sub_list
                }
                # 把当前数据进行缓存
                cache.set('sub_area_' + area_id, sub_data, 3600)
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'ok', 'sub_data': sub_data})