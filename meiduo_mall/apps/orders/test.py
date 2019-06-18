import json
from django import http
from django.db import transaction

from meiduo_mall.utils.response_code import RETCODE
from meiduo_mall.utils.views import LoginRequiredView
from users.models import Address
from django_redis import get_redis_connection
from goods.models import SKU
from decimal import Decimal
from django.shortcuts import render
from .models import OrderInfo, OrderGoods
from django.utils import timezone


class OrderSettlementView(LoginRequiredView):
    """去结算界面逻辑"""

    def get(self, request):
        # 查询数据（登陆用户的收货地址，展示购物车勾选商品的一些数据）
        # 获取地址对象
        addresses = Address.objects.filter(user=request.user)
        # 使用三目做一个判断，如果地址没有返回None
        addresses = addresses if addresses else None
        # 创建用户对象，创建redis连接对象，获取hash set数据
        user = request.user
        redis_conn = get_redis_connection('carts')
        redis_dict = redis_conn.hgetall('carts_%s' % user.id)
        selected_ids = redis_conn.smembers('selected_%s' % user.id)
        # 定义一个字典变量用来保存勾选的商品id和count
        cart_dict = {}
        for sku_id_bytes in selected_ids:
            cart_dict[int(sku_id_bytes)] = int(redis_dict[sku_id_bytes])
        # 获取勾选商品的sku模型
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        # 统计商品数量
        total_count = 0
        # 统计商品总价
        total_amount = Decimal('0.00')
        # 遍历商品查询集获取数量及总价
        for sku in sku_qs:
            sku.count = cart_dict[sku.id]
            sku.amount = sku.price * sku.count
            # 累加商品总量
            total_count += sku.count
            # 累加商品小计得到的商品总价
            total_amount += sku.amount
        # 运费
        freight = Decimal('0.00')
        # 构建模板需要渲染的数据
        context = {
            'addresses': addresses,
            'skus':sku_qs,
            'total_count': total_count,
            'total_amount': total_amount,
            'freight': freight,
            'payment_amount': total_amount + freight
        }
        # 响应
        return render(request, 'place_order.html', context)


class OrderCommitView(LoginRequiredView):
    """提交订单逻辑"""

    def post(self, request):
        # 四张表同时操作
        # 一、保存一个订单基本信息
        # 获取请求体数据（address_id, pay_method）
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = json_dict.get('pay_method')
        # 校验
        if all([address_id, pay_method]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return http.HttpResponseForbidden('地址不存在')
        # 判断pay_method  是否合法
        if pay_method not in [OrderInfo.PAY_METHODS_ENUM['CASH'], OrderInfo.PAY_METHODS_ENUM['ALIPAY']]:
            return http.HttpResponseForbidden('非法支付方式')
        # 生成用户对象
        user = request.user
        # 生成订单编号：获取当前时间 + 用户id
        order_id = timezone.now().strftime('%Y%m%d%H%M%S') + ('%09d' % user.id)
        # 保存订单基本信息OrderInfo
        status = OrderInfo.ORDER_STATUS_ENUM['UNPAID'] if OrderInfo.PAY_METHODS_ENUM['AILPAY'] else OrderInfo.ORDER_STATUS_ENUM['UNSEND']

        # 手动开启事务
        with transaction.atomic():
            # 创建事务的保存殿
            save_point = transaction.savepoint()
            try:
                # 保存订单信息
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address_id=address_id,
                    total_count=0,
                    total_amount=Decimal('0.00'),
                    freight=Decimal('10.00'),
                    pay_method=pay_method,
                    status=status
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
                # 遍历要购买的商品字典
                for sku_id in cart_dict:
                    while True:
                        # 一次值查询一个sku模型
                        sku = SKU.objects.filter(id=sku_id)
                        # 获取用户此商品的购买数量
                        buy_count = cart_dict[sku_id]
                        # 定义两个变量用来记录当前sku的原本库存和销量
                        origin_stock = sku.stock
                        origin_sales = sku.sales
                        # 判断当前要购买的商品库存是否充足
                        if buy_count > origin_stock:
                            # 库存不足就回滚
                            transaction.savepoint_rollback(save_point)
                            return http.HttpResponseForbidden('库存不足')


                        # 如果能够麦，计算新的库存和销量
                        new_stock = origin_stock - buy_count
                        new_sales = origin_sales + buy_count
                        # 修改sku模型库存和销量
                        # sku.stock = new_stock
                        # sku.sales = new_sales
                        # sku.save()
                        result = SKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=origin_stock, sales=new_sales)
                        if result == 0:
                            continue
                        # 三、修改spu的销量
                        spu = sku.spu
                        spu.sales += buy_count
                        spu.save()
                        # 四、保存订单中的商记录（为了保护商品订单与数量一致，将其放在for循环里面）
                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=buy_count,
                            price=sku.price,
                        )
                        # 累加商品总数量
                        order.total_count +=buy_count
                        order.total_amount +=(sku.price * buy_count)
                        # 累加商品总价
                        # 当前商品下单成功
                        break
                # 累加运费
                order.total_amount += order.freight
                order.save()
            # 暴力回流
            except Exception:
                transaction.savepoint_rollback(save_point)
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '下单失败'})
            else:
                transaction.savepoint_commit(save_point)
        # 删除已结算的购物车数据
        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *selected_ids)
        pl.srem('selected_%s' % user.id)
        pl.execute()
        # 响应
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
            OrderInfo.objects.get(id=order_id, total_amount=payment_amount, pay_method=paymethod)
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