from django.conf.urls import url

from . import views

urlpatterns = [
    # 购物车增删改查
    url(r'^carts/$', views.CartsView.as_view()),
    # 购物车全选
    url(r'^carts/selection/$', views.CartsSelectedAllView.as_view()),
    # 购物车精简版
    url(r'^carts/simple/$', views.CartsSimpleView.as_view()),

]
