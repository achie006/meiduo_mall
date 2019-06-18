import json

from django import http
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render
from meiduo_mall.utils.response_code import RETCODE
from django.utils import timezone
from django.views import View
from contents.utils import get_categories
from goods import models
from goods.models import SKU, GoodsCategory, GoodsVisitCount
from goods.utils import get_breadcrumb
from meiduo_mall.utils.response_code import RETCODE
from meiduo_mall.utils.views import LoginRequiredView
from meiduo_mall.utils.response_code import RETCODE
from orders.models import OrderInfo, OrderGoods
from users.models import User


class ListView(View):
    """商品列表页"""

    def get(self, request, category_id, page_num):
        # 判断category_id是否正确
        try:
            category = models.GoodsCategory.objects.get(id=category_id)
        except models.GoodsCategory.DoesNotExist:
            return http.HttpResponseNotFound('GoodsCategory does not exist')
        # 获取前端传入的排序参数
        sort = request.GET.get('sort')
        if sort == 'price':
            sort_field = 'price'
        elif sort == 'hot':
            sort_field = 'hot'
        else:
            sort = 'default'
            sort_field = '-create_time'

        # 获取当前三级商品中所有上架的商品
        # sku_qs = category.sku_set.filter(is_launched=True)
        sku_qs = SKU.objects.filter(category=category, is_launched=True).order_by(sort_field)
        # 创建分页对象Paginator(要分页的所有数据， 每页展示多少个数据)
        paginator = Paginator(sku_qs, 5)
        try:
            # 获取指定页面的数据
            page_skus = paginator.page(page_num)
        except EmptyPage:
            return http.HttpResponseForbidden('当前页面不存在')
        # 获取总页数
        total_page = paginator.num_pages

        # 查询商品频道分类
        # categories = get_categories()
        # # 查询面包屑导航
        # breadcrumb = get_breadcrumb(category)

        # 渲染页面
        context = {
            'categories': get_categories(),  # 商品频道分类
            'breadcrumb': get_breadcrumb(category),  # 面包屑导航
            'sort': sort,  # 排序字段
            'category': category,  # 第三级商品
            'page_skus': page_skus,  # 分页后数据
            'total_page': total_page,  # 总页数
            'page_num': page_num  # 当前页数

        }
        return render(request, 'list.html', context)


class HotGoodsView(View):
    """商品热搜排行"""

    def get(self, request, category_id):
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return http.HttpResponseForbidden('GoodsCategory does not exist')
        # 获取所有三级商品人气最高的两个数据
        sku_qs = SKU.objects.filter(category=category, is_launched=True).order_by('-sales')[:2]
        # 定义一个列表用来包装商品
        hots = []
        # 遍历查询集，将模型转换为字典
        for sku in sku_qs:
            hots.append({
                'id': sku.id,
                'name': sku.name,
                'price': sku.price,
                'default_image_url': sku.default_image.url
            })

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'ok', 'hot_skus': hots})


class DetailView(View):
    """商品详情界面"""

    def get(self, request, sku_id):

        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return render(request, '404.html')

        category = sku.category  # 获取当前sku所对应的三级分类

        # 查询当前sku所对应的spu
        spu = sku.spu

        """1.准备当前商品的规格选项列表 [8, 11]"""
        # 获取出当前正显示的sku商品的规格选项id列表
        current_sku_spec_qs = sku.specs.order_by('spec_id')
        current_sku_option_ids = []  # [8, 11]
        for current_sku_spec in current_sku_spec_qs:
            current_sku_option_ids.append(current_sku_spec.option_id)

        """2.构造规格选择仓库
        {(8, 11): 3, (8, 12): 4, (9, 11): 5, (9, 12): 6, (10, 11): 7, (10, 12): 8}
        """
        # 构造规格选择仓库
        temp_sku_qs = spu.sku_set.all()  # 获取当前spu下的所有sku
        # 选项仓库大字典
        spec_sku_map = {}  # {(8, 11): 3, (8, 12): 4, (9, 11): 5, (9, 12): 6, (10, 11): 7, (10, 12): 8}
        for temp_sku in temp_sku_qs:
            # 查询每一个sku的规格数据
            temp_spec_qs = temp_sku.specs.order_by('spec_id')
            temp_sku_option_ids = []  # 用来包装每个sku的选项值
            for temp_spec in temp_spec_qs:
                temp_sku_option_ids.append(temp_spec.option_id)
            spec_sku_map[tuple(temp_sku_option_ids)] = temp_sku.id

        """3.组合 并找到sku_id 绑定"""
        spu_spec_qs = spu.specs.order_by('id')  # 获取当前spu中的所有规格

        for index, spec in enumerate(spu_spec_qs):  # 遍历当前所有的规格
            spec_option_qs = spec.options.all()  # 获取当前规格中的所有选项
            temp_option_ids = current_sku_option_ids[:]  # 复制一个新的当前显示商品的规格选项列表
            for option in spec_option_qs:  # 遍历当前规格下的所有选项
                temp_option_ids[index] = option.id  # [8, 12]
                option.sku_id = spec_sku_map.get(tuple(temp_option_ids))  # 给每个选项对象绑定下他sku_id属性

            spec.spec_options = spec_option_qs  # 把规格下的所有选项绑定到规格对象的spec_options属性上

        context = {
            'categories': get_categories(),  # 商品分类
            'breadcrumb': get_breadcrumb(category),  # 面包屑导航
            'sku': sku,  # 当前要显示的sku模型对象
            'category': category,  # 当前的显示sku所属的三级类别
            'spu': spu,  # sku所属的spu
            'spec_qs': spu_spec_qs,  # 当前商品的所有规格数据
        }

        return render(request, 'detail.html', context)


class DetailVisitView(View):
    """统计商品类别每日访问量"""

    def post(self, request, category_id):

        # 校验category_id的真实有效性
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return http.HttpResponseForbidden('category_id不存在')
        # 创建时间对象获取到今天的日期
        today = timezone.now()

        try:
            # 在统计商品类别表中查询当前的类别在今天有没有访问过的记录
            goods_visit = GoodsVisitCount.objects.get(category=category, date=today)
        except GoodsVisitCount.DoesNotExist:
            # 如果查询不到说明今天此类别是第一次访问,  创建一个新的记录
            # goods_visit = GoodsVisitCount.objects.create(
            #     category=category
            # )
            goods_visit = GoodsVisitCount(category_id=category_id)
            # goods_visit = GoodsVisitCount()
            # goods_visit.category = category

        # 如果查询到说明今天此类别已经访问过 对原count+=1 save
        goods_visit.count += 1
        goods_visit.save()

        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


# class OrderShowView(LoginRequiredView):
#     """待支付订单展示"""
#     def get(self, request):
#         # 创建用户
#         user = request.user
#         # 取出用户名下的所有的order_ids
#         # 根据order_ids取出所有的订单信息即订单的查询集
#         order_qs = OrderInfo.objects.filter(user=user).order_by('update_time')
#         # 创建分页对象Paginator(要分页的所有数据， 每页展示多少个数据)
#         # paginator = Paginator(order_qs, 2)
#         # try:
#         #     # 获取指定页面的数据
#         #     page_num = paginator.page()
#         # except EmptyPage:
#         #     return http.HttpResponseForbidden('当前页面不存在')
#         # 获取总页数
#         # total_page = paginator.num_pages
#         page_orders = []
#         # 遍历查询集得出订单模型
#         for order in order_qs:
#             if order not in page_orders:
#                 order.sku_list = []
#                 order_id = order.order_id
#                 try:
#                     order_goods = OrderGoods.objects.filter(order_id=order_id)
#                 except OrderGoods.DoesNotExist:
#                     return
#
#                 for order_good in order_goods:
#                     sku_id = order_good.sku_id
#                     try:
#                         sku = SKU.objects.get(id=sku_id)
#                     except SKU.DoesNotExist:
#                         return
#                     sku.count = order_good.count
#                     print(type(sku.count))
#                     sku.amount = int(sku.price * sku.count)
#                     order.sku_list.append(sku)
#                 page_orders.append(order)
#
#         print(page_orders)
#         # for order in page_orders:
#         #     print(order.total_amount)
#         #     print(order.PAY_METHOD_CHOICES[order.status][1])
#         #     # print(order.pay_method_name)
#         #     order.status_name =
#         #     for sku in order.sku_list:
#         #         print(sku.default_image)
#         #         print(sku.name)
#         #         print(sku.price)
#         #         print(sku.count)
#         #         print(sku.amount)
#         #         break
#         #     break
#
#         # page_orders = [{order1}, {order2}, {order3}, {order4}]
#         #
#         # for order in page_orders：
#         #     for sku in order.sku_list:
#
#         return render(request, 'user_center_order.html', {'page_orders': page_orders})
#
#                 # sku.amount = sku.price * order.count.
#                 # 定义一个字典用来包装每一个订单信息
#                 # skus= {}
#                 # order_dict = {
#                 #     'id': order.order_id,
#                 #     'create_time': order.create_time,
#                 #     'status': order.status,
#                 #     'total_amount': order.total_amount,
#                 #     'freight': order.freight,
#                 #     'pay_method': order.pay_method,
#                 #     'skus': skus,
#                 # }
#                 # if order not in page_orders:
#                 #     page_orders[order] = {
#                 #         'id': order.order_id,
#                 #         'create_time': order.create_time,
#                 #         'status': order.status,
#                 #         'total_amount': order.total_amount,
#                 #         'freight': order.freight,
#                 #         'pay_method': order.pay_method,
#                 #         # 'skus': skus,
#                 #     }
#                 # 获取订单中的sku_id，根据sku_id获取sku查询集
#                 # order_ids = order.order_id
#                 # try:
#                 #     order_goods = OrderGoods.objects.get(order=order_ids)
#                 # except OrderGoods.DoesNotExist:
#                 #     return http.HttpResponseForbidden('order_id不存在')
#                 # try:
#                 #     sku = SKU.objects.get(name=order_goods)
#                 # except SKU.DoesNotExist:
#                 #     return http.HttpResponseForbidden('sku_name不存在')
#
#             # page_orders = {
#             #     ''
#             # }
#                 # 遍历sku查询集获取没有个sku信息
#
#                 # sku_id = sku.id
#                 # 定义一个包装sku的字典
#                 # if sku_id not in skus:
#                     # count = order_goods.count
#                     # skus[sku_id] = {
#                     #     'id': sku_id,
#                     #     'name': sku.name,
#                     #     'sku_default_image_url': sku.default_image.url,
#                     #     'price': sku.price,
#                     #     'count': count,
#                     #     'amount': sku.price * count,
#                     # }
#                 # 将订单所需要的信息包装在字典中
#                 # order_list.append(order_dict)


# class OrderCommitView(LoginRequiredView):
#     """待评价订单展示"""
#     def get(self, request):
#         return render(request, 'user_center_order.html')


class OrderShowView(LoginRequiredView):
    """展示全部订单"""

    def get(self, request, page_num):
        # 创建用户
        user = request.user
        # if user.is_authenticated:
        # 根据用户创建OrderInfo查询集
        order_qs = OrderInfo.objects.filter(user=user).order_by('-create_time')
        # 创建一个空列表page_orders用于包装最后的数据
        order_list = []
        # 遍历查询集得到每一个order
        for order in order_qs:
            # 给每一个order附加属性
            # 用切片给order附加paymethodname属性
            order.pay_method_name = order.PAY_METHOD_CHOICES[order.pay_method - 1][1]
            # 给order附加statusname
            order.status_name = order.ORDER_STATUS_CHOICES[order.status - 1][1]
            # 给order附加一个空列表用于添加order里面的sku
            order.sku_list = []
            # 根据order获取他的属性order_id
            order_id = order.order_id
            # 根据order_id获取ordergoods查询集
            try:
                order_goods = OrderGoods.objects.filter(order_id=order_id)
            except OrderGoods.DoesNotExist:
                return http.HttpResponseForbidden('order_id不存在')

            # 遍历ordergoods查询集获取ordergood
            for order_good in order_goods:
                # 根据ordergood中的sku_id获取sku对象
                sku_id = order_good.sku_id
                try:
                    sku = SKU.objects.get(id=sku_id)
                except SKU.DoesNotExist:
                    return http.HttpResponseForbidden('sku_id不存在')
                # 给sku对象附加count属性（通过ordergood的count获取）
                sku.count = order_good.count
                # 给sku对象附加amount属性（通过sku的price与count获取）
                sku.amount = sku.price * sku.count
                # 将sku对象追加到sku_list中
                order.sku_list.append(sku)
            # 将order对象追加到page——orders中
            order_list.append(order)
            # page_num = request.GET.get('page_num')
            # 创建分页对象Paginator(要分页的所有数据， 每页展示多少个数据)
            paginator = Paginator(order_qs, 2)
            try:
                # 获取指定页面的数据
                page_orders = paginator.page(page_num)
            except PageNotAnInteger:  # 如果 page 参数不为正整数，显示第一页
                page_orders = paginator.page(1)
            except EmptyPage:
                return http.HttpResponseForbidden('当前页面不存在')
            # 获取总页数
            total_page = paginator.num_pages
        context = {
            'page_num': page_num,
            'total_page': total_page,
            'page_orders': page_orders
        }
        # 渲染界面
        return render(request, 'user_center_order.html', context)


class GoodsCommentView(View):
    """获取商品评价信息"""
    def get(self, request, sku_id):
        # 根据sku_id获取所有的order_goods模型
        try:
            order_goods = OrderGoods.objects.filter(sku_id=sku_id)
        except OrderGoods.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')
        # 定义一个comments_list列表用来包装数据
        comments_list = []
        # 便利order_goods获取单独的ordergood
        for order_good in order_goods:
            # 获取前端需要的数据将包装在字典中追加给列表
            comments_list.append({
                'sku_id': sku_id,
                'comment': order_good.comment,
                'score': order_good.score,
                'is_anonymous': str(order_good.is_anonymous)
            })
        # context = {
        #     'comments_list': comments_list
        # }
        # 响应json
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'comments_list': comments_list})
