from django import http
from django.db import transaction
from django.shortcuts import render
from django_redis import get_redis_connection
import logging
from goods.models import SKU
from meiduo_mall.utils.views import LoginRequiredView
from users.models import Address as Addresses
from decimal import Decimal
import json
from django.utils import timezone
from .models import OrderInfo, OrderGoods
from meiduo_mall.utils.response_code import RETCODE

logger = logging.getLogger('django')


class OrderSettlementView(LoginRequiredView):
    """去结算界面逻辑"""

    def get(self, request):
        # 查询数据（登陆用户的收货地址，展示购物车中勾选商品的一些数据）
        # 获取地址对象
        addresses = Addresses.objects.filter(user=request.user, is_deleted=False)
        # 使用三目
        addresses = addresses if addresses.exists() else None
        user = request.user
        # 创建redis连接，获取hash和set数据
        redis_conn = get_redis_connection('carts')
        redis_dict = redis_conn.hgetall('carts_%s' % user.id)
        selected_ids = redis_conn.smembers('selected_%s' % user.id)
        # 定义一个字典变量用来保存勾选的商品id与count
        cart_dict = {}
        for sku_id_bytes in selected_ids:
            cart_dict[int(sku_id_bytes)] = int(redis_dict[sku_id_bytes])

        # 获取勾选商品中的sku模型
        skus = SKU.objects.filter(id__in=cart_dict.keys())
        # 统计商品数量
        total_count = 0
        # 商品总价
        total_amount = Decimal('0.00')
        for sku in skus:
            sku.count = cart_dict[sku.id]
            sku.amount = sku.price * sku.count

            # 累加商品总量
            total_count += sku.count
            # 累加商品小计得到商品总价
            total_amount += sku.amount
        # 运费
        freight = Decimal('10.00')
        # 构造模板需要渲染的数据
        context = {
            'addresses': addresses,
            'skus': skus,
            'total_count': total_count,
            'total_amount': total_amount,
            'freight': freight,
            'payment_amount': total_amount + freight
        }
        return render(request, 'place_order.html', context)


class OrderCommitView(LoginRequiredView):
    """提交订单逻辑"""

    def post(self, request):
        # 四张表同时操作，
        # 一、保存一个订单基本信息记录
        # 获取请求体数据
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = json_dict.get('pay_method')
        # 校验
        if all([address_id, pay_method]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            address = Addresses.objects.get(id=address_id)
        except Addresses.DoesNotExist:
            return http.HttpResponseForbidden('address_id不存在')
        # 判断pay_method是否合法
        if pay_method not in [OrderInfo.PAY_METHODS_ENUM['CASH'], OrderInfo.PAY_METHODS_ENUM['ALIPAY']]:
            return http.HttpResponseForbidden('非法支付方式')
        user = request.user
        # 生成订单编号: 获取当前时间 + 用户user_id
        order_id = timezone.now().strftime('%Y%m%d%H%M%S') + ('%09d' % user.id)
        # 保存订单基本信息OrderInfo
        status = (OrderInfo.ORDER_STATUS_ENUM['UNPAID']
                  if pay_method == OrderInfo.PAY_METHODS_ENUM['ALIPAY']
                  else OrderInfo.ORDER_STATUS_ENUM['UNSEND'])
        # 手动开启事务
        with transaction.atomic():
            # 创建事务的保存点
            save_point = transaction.savepoint()
            try:
                # 保存订单记录
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=address,
                    total_count=0,
                    total_amount=Decimal('0.00'),
                    freight=Decimal('10.00'),
                    pay_method=pay_method,
                    status=status,
                )
                # 二、修改sku的库存和销量
                # 从redis读取购物车中被勾选的商品信息
                redis_conn = get_redis_connection('carts')
                redis_dict = redis_conn.hgetall('carts_%s' % user.id)
                selected_ids = redis_conn.smembers('selected_%s' % user.id)
                # 定义一个字典用来包装要购买商品的id和count
                cart_dict = {}
                # 遍历set集合包装数据
                for sku_id_bytes in selected_ids:
                    cart_dict[int(sku_id_bytes)] = int(redis_dict[sku_id_bytes])
                # 遍历要购买的商品的字典
                for sku_id in cart_dict:
                    while True:
                        # 一次只查询一个sku模型
                        sku = SKU.objects.get(id=sku_id)
                        # 获取用户此商品腰骨埋的数据
                        buy_count = cart_dict[sku_id]
                        # 低昂以两个变量用来记录当前sku的原本库存和销量
                        origin_stock = sku.stock
                        origin_sales = sku.sales

                        # 判断当前要购买的商品库存是否充足
                        if buy_count > origin_stock:
                            # 库存不足就回滚
                            transaction.savepoint_rollback(save_point)
                            # 如果库存不足，提前响应
                            return http.JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '库存不足'})
                        # 如果能购买，计算新的库存和销量
                        new_stock = origin_stock - buy_count
                        new_sales = origin_sales + buy_count
                        # 修改sku模型库存和销量
                        # sku.stock = new_stock
                        # sku.sales = new_sales
                        # sku.save()
                        result = SKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock,
                                                                                          sales=new_sales)
                        if result == 0:
                            continue
                        # 三、修改spu的销量
                        spu = sku.spu
                        spu.sales += buy_count
                        spu.save()
                        # 四、保存订单中的商品记录(为了保持商品订单与商品数量一指，将其放在for循环里面)
                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=buy_count,
                            price=sku.price,

                        )
                        # 累加商品总数量
                        order.total_count += buy_count
                        # 累加商品总量
                        order.total_amount += (sku.price * buy_count)
                        # 当前商品下蛋成功
                        break
                # 累加运费
                order.total_amount += order.freight
                order.save()

                #
            except Exception:
                # 暴力回流
                transaction.savepoint_rollback(save_point)
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '下单失败'})
            else:
                transaction.savepoint_commit(save_point)
        # 删除以结算的购物车数据
        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *selected_ids)
        pl.delete('selected_%s' % user.id)  # 删除整个集合
        # pl.srem('selected_%s' % user.id, *selected_ids)   删除set集合中的元素
        pl.execute()
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '下单成功', 'order_id': order_id})


class OrderSuccessView(LoginRequiredView):
    """提交订单成功后的页面"""

    def get(self, request):
        # 接受查询参数数据
        query_dict = request.GET
        order_id = query_dict.get('order_id')
        payment_amount = query_dict.get('payment_amount')
        pay_method = query_dict.get('pay_method')

        # 校验
        try:
            OrderInfo.objects.get(order_id=order_id, total_amount=payment_amount, pay_method=pay_method)
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden('订单信息有误')
        # 包装模板要进行渲染的数据
        context = {
            'order_id': order_id,
            'pay_method': pay_method,
            'payment_amount': payment_amount
        }
        # 响应
        return render(request, 'order_success.html', context)


class OrderGoodsView(LoginRequiredView):
    """商品评论"""

    def get(self, request):
        order_id = request.GET.get('order_id')
        # 根据前端路由传递的order_id获取ordergoods信息
        try:
            order_goods = OrderGoods.objects.filter(order_id=order_id)
        except OrderGoods.DoesNotExist:
            return http.HttpResponseForbidden('order_id不存在')
        skus = []
        for order_good in order_goods:
            sku_id = order_good.sku_id
            try:
                sku = SKU.objects.get(id=sku_id)
            except SKU.DoesNotExist:
                return http.HttpResponseForbidden('sku_id不存在')
            skus.append({
                'sku_id': sku_id,
                'name': sku.name,
                'price': str(sku.price),
                'default_image_url': sku.default_image.url,
                'order_id': order_id
            })
        context = {'uncomment_goods_list': skus}
        # 响应
        return render(request, 'goods_judge.html', context)

    def post(self, request):
        # 接受数据
        qurey_dict = json.loads(request.body.decode())
        order_id = qurey_dict.get('order_id')
        sku_id = qurey_dict.get('sku_id')
        comment = qurey_dict.get('comment')
        score = qurey_dict.get('score')
        is_anonymous = qurey_dict.get('is_anonymous')
        # 校验数据
        if all([order_id, sku_id, score, comment]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            order = OrderGoods.objects.get(sku_id=sku_id, order_id=order_id)
        except OrderGoods.DoesNotExist:
            return http.HttpResponseForbidden('order_id不存在')
        if isinstance(is_anonymous, bool) and isinstance(score, int) is False:
            return http.HttpResponseForbidden('参数格式不正确')
        if len(comment) < 5:
            return http.HttpResponseForbidden('评论不足5个字')
        # 将前端的数据保存到数据库
        # 修改两个表，Order_Goods跟SKU
        # 将score, comment, is_anonymous
        order.score = score
        order.is_anonymous = is_anonymous
        order.comment = comment
        order.is_commented = True
        order.save()
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')
        sku.comments += 1
        sku.save()

        # return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '评论成功'})
        # 响应json数据
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '评论成功'})
