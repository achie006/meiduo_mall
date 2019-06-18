from goods.models import GoodsChannel


def get_categories():
    """查询出商品数据类别"""
    # 定义一个字典变量用于保存数据
    categories = {}
    # 获取商品种类查询集
    goods_channels_qs = GoodsChannel.objects.all().order_by('group_id', 'sequence')
    # 遍历查询集获取一级数据
    for channel in goods_channels_qs:
        # 获取一级数据的组号
        group_id = channel.group_id
        # 判断改组号是否创建空字典
        if group_id not in categories:
            # 若为新组号则以该组号为建创建字典
            categories[group_id] = {'channels': [], 'sub_cats': []}
        # 根据获取到的频道获取该频道的一级商品
        cat1 = channel.category
        # 将频道中的url赋值给cat1
        cat1.url = channel.url
        # 将cat1添加到字典channels的列表中
        categories[group_id]['channels'].append(cat1)
        # 获取当前cat1下的cat2查询集
        cat2_qs = cat1.subs.all()
        # 遍历cat2的查询集
        for cat2 in cat2_qs:
            # 根据当前的cat2获取cat3的查询集
            cat3_qs = cat2.subs.all()
            # 将得到的cat3_qs查询集赋值给cat2的sub_cats
            cat2.sub_cats = cat3_qs
            # 将cat2添加到二级中的sub_cats的列表中
            categories[group_id]['sub_cats'].append(cat2)

    return categories
