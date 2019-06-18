import base64, pickle
from django_redis import get_redis_connection


def merge_cart_cookie_to_redis(request, response):

    # 获取出cookie购物车数据
    cart_str = request.COOKIES.get('carts')
    # 注意：必须在执行完login之后再去拿user不然就是匿名用户
    user = request.user
    # 判断有没有cookie购物车数据，如果有天前响应
    if cart_str is None:
        return
    # 将cookie_str转成dict
    cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))

    # 创建redis连接对象
    redis_conn = get_redis_connection('carts')
    # 管道技术
    pl = redis_conn.pipeline()
    # 遍历cookie大字典
    for sku_id, sku_dict in cart_dict.items():
        # 使用hset添加hash数据
        pl.hset('carts_%s' % user.id, sku_id, sku_dict['count'])
        # sadd或者srem来操作勾选状态
        if sku_dict['selected']:
            pl.sadd('selected_%s' % user.id, sku_id)
        else:
            pl.srem('selected_%s' % user.id, sku_id)
    pl.execute()
    # 删除cookie中的数据
    response.delete_cookie('carts')

