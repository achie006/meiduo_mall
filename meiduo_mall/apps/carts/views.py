import base64
import json
import pickle
from meiduo_mall.utils.response_code import RETCODE
from django import http
from django.shortcuts import render
from django.views import View
from django_redis import get_redis_connection
from goods.models import SKU


class CartsView(View):
    """购物车管理"""

    def post(self, request):
        """添加购物车"""
        # 接收请体中的sku_id和count
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected', True)
        # 校验
        if all([sku_id, count]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseNotFound('sku_id不存在')

        # 判断count是不是int类型
        if isinstance(count, int) is False:
            return http.HttpResponseForbidden('参数格式不正确')
        # 获取当前请求对象中的user
        user = request.user
        # 判断用户是否登陆
        if user.is_authenticated:
            # 如果是登陆用户操作redis购物车数据
            """
            hash:{sku_id_1:1., sku_id_16: 2}
            set: {sku_id_1}
            """
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 管道
            pl = redis_conn.pipeline()
            # 向hash中添加sku_id及count hincrby
            pl.hincrby('carts_%s' % user.id, sku_id, count)
            # 把当前商品的sku_id添加到set集合
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            # 执行管道
            pl.execute()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})

        # 如果未登录用户操作cookie购物车数据
        else:
            # 先获取cookie中的购物车数据
            cart_str = request.COOKIES.get('carts')
            # 判断是否有cookie购物车数据
            if cart_str:
                # 如果有cookie购物车数据，应该将字符串转会字典
                # 先将字典转换为bytes类型
                cart_str_bytes = cart_str.encode()
                # 使用base64把bytes字符串转换成bytes类型
                cart_bytes = base64.b64decode(cart_str_bytes)
                # 使用pickle模型把bytes转换成字典
                cart_dict = pickle.loads(cart_bytes)
                # cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
                # 如果cookie中没有购物车数据，准备一个新字典用来装购物车和苏剧
            else:
                cart_dict = {}
            # 判断本次添加的购物车商品是否之前已存在，已存在要做增量计算
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
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})
            # 设置cookie
            response.set_cookie('carts', cart_str)
            # 响应
        return response

    def get(self, request):
        """展示购物车"""
        # 判断用户是否登陆
        user = request.user
        if user.is_authenticated:
            # 登陆操作redis购物车数据
            # 把redis购物车中hash和set集合数据取出来
            redis_conn = get_redis_connection('carts')
            # 获取redis的hash字典数据：
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            # 获取set集合
            selected_ids = redis_conn.smembers('selected_%s' % user.id)
            # 把数据格式转换成和cookie购物车水浒u格式一致，方便后期统一处理
            # 定义一个字典用于装redis购物车的所有数据
            cart_dict = {}
            # 遍历hash字典数据向cart_dict添加
            for sku_id_bytes in redis_dict:
                cart_dict[int(sku_id_bytes)] = {
                    'count': int(redis_dict[sku_id_bytes]),
                    'selected': sku_id_bytes in selected_ids,
                }

        else:
            # 未登录操作cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 如果没有去到cookie值
                return render(request, 'cart.html')

        # 通过cart_dict中的key   sku_id获取sku模型
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        # 用来包装每一个购物车商品字典数据
        sku_list = []
        # 将sku模型和商品的其他数据包装到同一个字典中
        for sku_model in sku_qs:
            count = cart_dict[sku_model.id]['count']
            sku_list.append({
                'id': sku_model.id,
                'name': sku_model.name,
                'price': str(sku_model.price),
                'default_image_url': sku_model.default_image.url,
                'selected': str(cart_dict[sku_model.id]['selected']),
                'count': count,
                'amount': str(sku_model.price * count),
            })
        return render(request, 'cart.html', {'cart_skus': sku_list})

    def put(self, request):
        """修改购物车"""
        # 接受前端请求体sku_id,count,selected
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

        try:
            count = int(count)
        except Exception:
            return http.HttpResponseForbidden('数据格式不正确')

        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('类型有误')
        # 包装一个当前修改的商品数据字典
        cart_sku = {
            'id': sku.id,
            'name': sku.name,
            'price': str(sku.price),
            'default_image_url': sku.default_image.url,
            'selected': selected,
            'count': count,
            'amount': str(sku.price * count),
        }
        # 判断是否登陆
        user = request.user
        if user.is_authenticated:

            # 登陆用户修改redis购物车数据
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 管道技术
            pl = redis_conn.pipeline()
            # 修改hash数据
            pl.hset('carts_%s' % user.id, sku_id, count)
            # 修改set聚合数据
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            else:
                pl.srem('selected_%s' % user.id, sku_id)
            # 执行管道
            pl.execute()
            # 包装一个当前修改的商品数据字典
            # cart_sku = {
            #     'id': sku.id,
            #     'name': sku.name,
            #     'price': str(sku.price),
            #     'default_url': sku.default_image.url,
            #     'selected': selected,
            #     'count': count,
            #     'amount': str(sku.price * count),
            # }
            # 响应
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车数据车成功', 'cart_sku': cart_sku})
            # return response

        else:
            # 未登录用户修该cookie购物车数据
            # 获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 把cart_str转换成字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'cookie数据没有获取到'})

            # 新数据赋值修改
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected,
            }
            # 把字典转换成字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 包装一个当前修改的商品数据字典
            # cart_sku = {
            #     'id': sku.id,
            #     'name': sku.name,
            #     'price': str(sku.price),
            #     'default_url': sku.default_image.url,
            #     'selected': selected,
            #     'count': count,
            #     'amount': str(sku.price * count),
            # }
            # 设置cookie
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车数据车成功', 'cart_sku': cart_sku})
            response.set_cookie('carts', cart_str)
            # 响应
            # return response
        return response

    def delete(self, request):
        """删除购物车"""
        # 接受请求体中的sku_id
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
            # 登陆操作redis数据
            # 创建redis的连接对象
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            # 删除hash中的对应键值对
            pl.hdel('carts_%s' % user.id, sku_id)
            # 把当前sku_id从set集合中一出
            pl.srem('selected_%s' % user.id, sku_id)
            pl.execute()
            # 响应
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '购物车删除成功'})
        else:
            # 未登录操作cookie数据
            # 先获取cookie购物车数据

            cart_str = request.COOKIES.get('carts')
            # 判断是否获取到cookie购物车数据
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 获取到之后字符串转换成字典
                # 魅惑去到提前响应
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': 'cookie数据没获取到'})
                # 删除指定sku_id对应的键值对
            if sku_id in cart_dict:
                del cart_dict[sku_id]
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除购物车成功'})
            # 判断当前字典是否为空，如果为空将cookie删除
            if not cart_dict:
                # 删除cookie，删除cookie的原理，实际就是在设置cookie把它的过期时间改为0
                response.delete_cookie('carts')
                return response
            # 字典转字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 设置cookie
            response.set_cookie('carts', cart_str)
            # 响应
        return response


class CartsSelectedAllView(View):
    """购物车全选"""

    def put(self, request):
        # 接受请求体数据
        json_dict = json.loads(request.body.decode())
        selected = json_dict.get('selected')
        # 校验
        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('参数格式不正确')
        # 判断登陆
        user = request.user
        if user.is_authenticated:
            # 登陆操作redis
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 获取hash
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            # 如果时全选将hash中的所有key添加到set集合中
            if selected:
                redis_conn.sadd('selected_%s' % user.id, *redis_dict.keys())
            # 如果是取消全选将set删除
            else:
                redis_conn.delete('selected_%s' % user.id)
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除购物车成功'})

        else:
            # 未登录操作cookie
            # 先获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            # 判断是否获取到
            if cart_str:
                # 如果获取到把字符串转成字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            # 如果没有获取到提前响应
            else:
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': 'cookie没有获取到'})
            # 遍历cookie购物车大字典，将内部的每一个selected修改为True或者False
            for sku_id in cart_dict:
                cart_dict[sku_id]['selected'] = selected
            # 把字典转换成字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除购物车成功'})
            # 设置cookie
            response.set_cookie('carts', cart_str)
        # 响应
        return response


class CartsSimpleView(View):
    """展示精简版购物车数据"""

    def get(self, request):
        # 判断用户是否登陆
        user = request.user
        if user.is_authenticated:
            # 登陆操作redis购物车数据
            # 把redis购物车中hash和set集合数据取出来
            redis_conn = get_redis_connection('carts')
            # 获取redis的hash字典数据：
            redis_dict = redis_conn.hgetall('carts_%s' % user.id)
            # 获取set集合
            selected_ids = redis_conn.smembers('selected_%s' % user.id)
            # 把数据格式转换成和cookie购物车水浒u格式一致，方便后期统一处理
            # 定义一个字典用于装redis购物车的所有数据
            cart_dict = {}
            # 遍历hash字典数据向cart_dict添加
            for sku_id_bytes in redis_dict:
                cart_dict[int(sku_id_bytes)] = {
                    'count': int(redis_dict[sku_id_bytes]),
                    'selected': sku_id_bytes in selected_ids,
                }

        else:
            # 未登录操作cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 如果没有去到cookie值
                return render(request, 'cart.html')

        # 通过cart_dict中的key   sku_id获取sku模型
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        # 用来包装每一个购物车商品字典数据
        sku_list = []
        # 将sku模型和商品的其他数据包装到同一个字典中
        for sku_model in sku_qs:
            count = cart_dict[sku_model.id]['count']
            sku_list.append({
                'id': sku_model.id,
                'name': sku_model.name,
                'default_image_url': sku_model.default_image.url,
                'count': count,
            })
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'cart_skus': sku_list})