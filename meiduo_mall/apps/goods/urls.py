from django.conf.urls import url

from . import views

urlpatterns = [
    # 商品列表界面
    url(r'^list/(?P<category_id>\d+)/(?P<page_num>\d+)/$', views.ListView.as_view()),
    # 商品热销排行
    url(r'^hot/(?P<category_id>\d+)/$', views.HotGoodsView.as_view()),
    # 商品详情
    url(r'^detail/(?P<sku_id>\d+)/$', views.DetailView.as_view()),
    # 商品类别访问量统计
    url(r'^visit/(?P<category_id>\d+)/$', views.DetailVisitView.as_view()),
    # 商品订单待评价
    # url(r'^orders/comment/?order_id=(?P<order_id>\d+)/$', views.OrderCommentView.as_view()),
    # 商品订单页面展示
    url(r'^orders/info/(?P<page_num>\d+)/$', views.OrderShowView.as_view()),
    # 获取商品评价信息
    url(r'^comments/(?P<sku_id>\d+)/$', views.GoodsCommentView.as_view()),


]