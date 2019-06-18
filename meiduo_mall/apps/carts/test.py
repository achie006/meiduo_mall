import base64
import json
import pickle

from django import http
from django.shortcuts import render
from django.views import View
from django_redis import get_redis_connection

from goods.models import SKU
from meiduo_mall.utils.response_code import RETCODE


class CartsView(View):
    """购物车管理"""

    def post(self, request):
        """添加购物车"""
        # 接受请求体中的数据sku_id,count
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected')
        # 校验
        if all([sku_id, count]) is False:
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '缺少必传参数'})
        # 校验sku_id
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')
        # 判断count是不是int类型
        if isinstance(count, int) is False:
            return http.HttpResponseForbidden('count格式不正确')

        # 判断用户是否登陆
        user = request.user
        if user.is_authenticated:
            # 登陆用户操作redis
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 管道技术
            pl = redis_conn.pipeline()
            # 向hash中添加sku_id根count
            pl.hincoby('cart_%s' % user.id, sku_id, count)
            # 将sku_id添加到set集合
            pl.sadd('selected_%s' % user.id, selected)
            # 执行管道
            pl.execute()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})
        else:
            # 未登录用户操作cookie
            # 先获取cookie中的数据，字符串形式
            cart_str = request.COOKIES.get('carts')
            # 判断是否有cookie数据
            if cart_str:
                # 如果有cookie购物车数据，应该将字符串转为字典
                # 先将字符串转换为bytes类型
                cart_str_bytes = cart_str.encode()
                # 使用base64把bytes字符串转换成bytes64类型
                cart_bytes = base64.b64decode(cart_str_bytes)
                # 使用pickle模型把bytes64转换成字典
                cart_dict = pickle.loads(cart_bytes)
            else:
                # 如果cookie没有购物车数据，准备一个新字典用来装购物车
                cart_dict = {}
            # 判断本次添加的购物车是否之前已存在，已存在要做增量计算
            if sku_id in cart_dict:
                # 获取存在商品的原有count
                origin_count = cart_dict[sku_id]['count']
                count += origin_count
            # 如果是一个新商品直接添加到字典
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected,
            }
            # 把cookie购物车字典转换成字符串
            cart_str = base64.b64encode(pickle.loads(cart_dict)).decode()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})
            # 通过响应对象设置cookie
            response.set_cookie('carts', cart_str)
        # 响应
        return response

    def get(self, request):
        """展示购物车"""
        # 判断用户是否登陆
        user = request.user
        if user.is_authenticated:
            # 登陆操作redis购物车数据
            # 把redis购物车中的hash根set聚合数据取出来
            redis_conn = get_redis_connection('carts')
            # 获取redis购物车中的hash字典数据
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            # 获取redis中的set
            selected_ids = redis_conn.smembers('selected_%s' % user.id)
            # 把数据格式转换成和cookie购物车中数据格式一致，方便后期统一处理
            # 定义一个字典用于包装redis数据
            cart_dict = {}
            # 遍历hash数据向cart_dict中添加
            for sku_id in cart_dict:
                cart_dict[int(sku_id)] = {
                    'count': int(cart_dict[sku_id]),
                    'selected': sku_id in selected_ids,
                }
        else:
            # 未登录操作cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            # 判断cookie中是否有值
            if cart_str:
                # 如果有值将字符串转换成字典形式
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 如果没有返回渲染
                return render(request, 'cart.html')
        # 通过cart_dict中的sku_id获取sku模型查询集
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        # 用来包装每一个购物车数据的列表
        sku_list = []
        # 将sku模型和商品的其他数据包装同一个字典中
        for sku_model in sku_qs:
            count = cart_dict[sku_model.id]['count']
            sku_list.append({
                'id': sku_model.id,
                'name': sku_model.name,
                'price': str(sku_model.price),
                'default_image_url': sku_model.default_image.url,
                'selected': str(cart_dict[sku_model,id]['selected']),
                'count': count,
                'amount': str(sku_model.price * count)
            })
        # 渲染界面
        return render(request, 'cart.html', {'cart_skus': sku_list})

    def put(self, request):
        """修改购物车"""
        # 接受请求体数据sku_id,count, selected
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected')
        # 校验
        if all([sku_id, count]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')
        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('参数格式不正确')
        try:
            count = int(count)
        except Exception:
            return http.HttpResponseForbidden('参数格式不正确')
        # 包装一个当前修改的商品数据字典
        cart_sku = {
            'id': sku.id,
            'name': sku.name,
            'price': str(sku.price),
            'default_image_url': sku.default_image.url,
            'count': count,
            'selceted': selected,
            'amount': str(sku.price * count),
        }
        # 判断是否登陆
        user = request.user
        if user.is_authenticated:
            # 登陆操作redis购物车数据
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 管道技术
            pl = redis_conn.pipeline
            # 修改hash数据
            pl.hset('cart_%s' % user.id, sku_id, count)
            # 修改set聚合数据
            # 判断selected时不时True
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            else:
                pl.srem('selected_%s' % user.id, sku_id)
            # 执行管道
            pl.execute()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车成功'})
        else:
            # 未登录操作cookie购物车数据
            # 获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            # 判断是否存在cart_str的值
            if cart_str:
                # 把cart_str转换成cart_dict
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 如果没有值响应
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '修改购物车失败'})
            # 新数据赋值修改
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected,
            }
            # 把字典转换成字符串
            cart_str = base64.b64encode(pickle.loads(cart_dict)).decode()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车成功'})
            # 设置cookie
            response.set_cookie('carts', cart_dict)
        # 响应
        return response


    def delete(self, request):
        """删除购物车"""
        # 接受请求体内的数据sku_id
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')

        # 校验
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')
        # 判断登陆
        user = request.user
        if user.is_authenticated:
            # 登陆创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 管道技术
            pl = redis_conn.pipeline()
            # 删除hash中的对应键值对
            pl.hdel('cart_%s' % user.id, sku_id)
            # 把当前sku_id从set中删除
            pl.srem('selected_%s' % user.id, sku_id)
            pl.execute()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除购物车成功'})
        else:
            # 未登录获取cookie中的数据
            cart_str = request.COOKIES.get('carts')
            # 判断有值将字符串转换成字典
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 为获取直接响应
                return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'cookie数据没有获取到'})
            # 删除指定sku_id对应的键值对
            if sku_id in cart_dict:
                del cart_dict[sku_id]
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除购物车成功'})
            # 判断当前字典是否为空，如果为空将cookie删除
            if not cart_dict:
                response.delete_cookie('carts')
                return response
            # 字典转换成字符串形式
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 设置cookie
            response.set_cookie('carts', cart_str)

        # 响应
        return response


class CartsSelectedView(View):
    """购物车全选"""

    def put(self, request):
        # 接受请求体数据
        json_dict = json.loads(request.body.decode())
        selected = json_dict.get('selected')
        # 校验
        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('参数格式有误')
        # 判断登陆
        user = request.user
        if user.is_authenticated:
            # 登陆用户连接redis
            redis_conn = get_redis_connection('carts')
            # 获取hash数据
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            # 做一个判断，如果是全选，将hash中的所有key添加到set集合
            if selected:
                redis_conn.sadd('selected_%s' % user.id, *redis_dict.keys())
            # 如果不是全选，将set集合删除
            else:
                redis_dict.delete('selected_%s' % user.id)
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '更改状态成功'})
        else:
            # 未登录用户获取cookie数据
            cart_str = request.COOKIES.get('carts')
            # 判断是否获取到
            if cart_str:
                # 获取到数据将字符串转换成字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 未获取到数据提前响应
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '未获去到cookie'})
            # 遍历cookie字典，将内部的每一个selected修改为True或者False
            for sku_id in cart_dict:
                cart_dict[sku_id]['selected'] = selected
            # 将cookie字典转换成字符串形式
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 创建连接对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'cookie操作成功'})
            # 用响应对象设置cookie
            response.set_cookie('carts', cart_str)
        # 响应
        return response


def merge_cart_cookie_to_redis(request, response):
    # 获取出cookie购物车数据
    cart_str = request.COOKIES.get('carts')
    # 注意： 在login之后在获取user，否则得到的是匿名用户
    user = request.user
    # 判断有没有cookie数据，如果没有就直接响应
    if cart_str is None:
        return
    # 将cookie字符串转换成字典
    cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
    # 创建redis连接对象
    redis_conn = get_redis_connection(('carts'))
    # 管道技术
    pl = redis_conn.pipeline()
    # 遍历cookie字典获取sku_id与sku_dict
    for sku_id, sku_dict in cart_dict.items:
        # 通过hset修改redis 0hash中的数据
        pl.hset('carrs_%s' % user.id, sku_id)
        # 在通过sadd或者srem来修改set集合
        if sku_dict['selected']:
            pl.sadd('selected_%s' % user.id)
        else:
            pl.srem('selected_%s' % user.id)
    # 执行管道技术
    pl.execute()
    # 删除cookie中的数据
    response.delete_cookie('carts')


class CartsSimpleView(View):
    """展示精简版购物车数据"""

    def get(self, request):
        # 判断用户是否登陆
        user = request.user
        if user.is_authenticated:
            # 登陆用户操作redis购物车
            redis_conn = get_redis_connection(('carts'))
            # 获取到redis中的hash数据
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            # 获取到set集合的数据
            selected_ids = redis_conn.smembers('selected_%s' % user.id)
            # 将数据转换成与cookie一致的数据格式方便后期统一处理‘

            # 定义一个字典用于庄redis购物车的所有数据
            cart_dict = {}
            # 遍历hash数据字典cart_dict添加
            for sku_id_bytes in redis_dict:
                cart_dict[int(sku_id_bytes)] = {
                    'count': int(redis_dict[sku_id_bytes]),
                    'selected': sku_id_bytes in selected_ids
                }
        else:
            # 未登录用户操作cookie数据
            cart_str = request.COOKIES.get('carts')
            # 如果有值将字符串转换成字典形式
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            # 如果没有值提前响应
            else:
                return render(request, 'cart.html')
        # 通过cart_dict中的key  sku_id 获取sku模型
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        # 定义一个用来包装购物车商品字典数据的类表
        sku_list = []
        # 将sku模型和商品的其他数据包装到同一个字典中
        for sku_model in sku_qs:
            count = cart_dict[sku_model.id]['count']
            sku_list.append({
                'id': sku_model.id,
                'name': sku_model.name,
                'default_image_url': sku_model.default_image.url,
                'count': count
            })
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'cart_skus': sku_list})
        # 响应